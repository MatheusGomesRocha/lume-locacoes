<?php

namespace App\Http\Controllers;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Grupo;
use App\Support\Acesso;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/** Listar: administradores (para escolher o grupo ao cadastrar usuários). Criar, editar e excluir: só o master. */
class GrupoController extends Controller
{
    private function paraApi(Grupo $g): array
    {
        return [
            'id' => $g->id, 'nome' => $g->nome, 'descricao' => $g->descricao, 'permissoes' => Acesso::limpar($g->permissoes ?? []),
            'sistema' => $g->sistema, 'usuarios_count' => $g->usuarios_count ?? $g->usuarios()->count(),
        ];
    }

    private function regras(?int $ignorar = null): array
    {
        return [
            'nome' => ['required', 'string', 'max:100', Rule::unique('grupos', 'nome')->ignore($ignorar)],
            'descricao' => 'nullable|string|max:255',
            'permissoes' => 'present|array',
            'permissoes.*' => 'string',
        ];
    }

    public function index()
    {
        return Grupo::withCount('usuarios')->orderBy('id')->get()->map(fn ($g) => $this->paraApi($g));
    }

    public function store(Request $request): JsonResponse
    {
        $d = $request->validate($this->regras());
        $g = Grupo::create(['nome' => trim($d['nome']), 'descricao' => $d['descricao'] ?? null, 'permissoes' => Acesso::limpar($d['permissoes']), 'sistema' => false]);

        return response()->json($this->paraApi($g), 201);
    }

    public function update(Request $request, Grupo $grupo): array
    {
        if ($grupo->sistema) {
            throw new RegraDeNegocioException('O grupo Master não pode ser alterado.', [], 403);
        }
        $d = $request->validate($this->regras($grupo->id));
        $grupo->update(['nome' => trim($d['nome']), 'descricao' => $d['descricao'] ?? null, 'permissoes' => Acesso::limpar($d['permissoes'])]);

        return $this->paraApi($grupo);
    }

    public function destroy(Grupo $grupo)
    {
        if ($grupo->sistema) {
            throw new RegraDeNegocioException('O grupo Master não pode ser excluído.', [], 403);
        }
        if ($grupo->usuarios()->exists()) {
            throw new RegraDeNegocioException('Este grupo tem usuários. Mude o grupo deles antes de excluir.', [], 409);
        }
        $grupo->delete();

        return response()->noContent();
    }
}
