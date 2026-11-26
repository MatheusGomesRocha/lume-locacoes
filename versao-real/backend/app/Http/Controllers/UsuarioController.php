<?php

namespace App\Http\Controllers;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Grupo;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

/**
 * Hierarquia:
 *  - master: cadastra e edita admins e usuários; só ele altera os próprios dados (nome, e-mail e senha); não é excluído;
 *  - admin: cadastra e edita só usuários comuns (sempre como "usuário"); não mexe no master nem em outros admins;
 *  - usuário: não gerencia ninguém.
 * Toda pessoa tem exatamente um grupo, e o grupo Master é só do master.
 */
class UsuarioController extends Controller
{
    private function ator(Request $r): Usuario
    {
        return $r->attributes->get('usuario');
    }

    private function falha(string $campo, string $mensagem): never
    {
        throw ValidationException::withMessages([$campo => [$mensagem]]);
    }

    private function regras(Request $r, ?Usuario $alvo, bool $criando): array
    {
        $r->merge(['email' => mb_strtolower(trim((string) $r->input('email')))]);

        return [
            'nome' => 'required|string|max:150',
            'email' => ['required', 'email', 'max:150', Rule::unique('usuarios', 'email')->ignore($alvo?->id)],
            'senha' => [$criando ? 'required' : 'nullable', 'string', 'min:8', 'max:200'],
            'papel' => ['required', Rule::in([Usuario::ADMIN, Usuario::USUARIO])],
            'grupo_id' => ['required', 'integer', Rule::exists('grupos', 'id')],
            'ativo' => 'required|boolean',
        ];
    }

    private function conferirGrupo(int $grupoId): void
    {
        if (Grupo::whereKey($grupoId)->value('sistema')) {
            $this->falha('grupo_id', 'O grupo Master é só do master.');
        }
    }

    public function index()
    {
        return Usuario::with('grupo')->orderBy('nome')->get()->map->paraApi();
    }

    public function store(Request $request): JsonResponse
    {
        $ator = $this->ator($request);
        if ($request->input('papel') === Usuario::MASTER) {
            $this->falha('papel', 'Só existe um master.');
        }
        if ($ator->papel !== Usuario::MASTER) {
            $request->merge(['papel' => Usuario::USUARIO]); // admin nunca cria admin
        }
        $d = $request->validate($this->regras($request, null, true));
        $this->conferirGrupo((int) $d['grupo_id']);

        $u = Usuario::create([
            'nome' => trim($d['nome']), 'email' => $d['email'], 'senha' => Hash::make($d['senha']),
            'papel' => $d['papel'], 'grupo_id' => $d['grupo_id'], 'ativo' => $d['ativo'],
        ]);

        return response()->json($u->load('grupo')->paraApi(), 201);
    }

    public function update(Request $request, Usuario $usuario): array
    {
        $ator = $this->ator($request);

        if ($usuario->papel === Usuario::MASTER && $ator->id !== $usuario->id) {
            throw new RegraDeNegocioException('Só o próprio master pode alterar os dados do master.', [], 403);
        }
        if ($usuario->papel !== Usuario::MASTER && ! Acesso::podeGerenciar($ator, $usuario)) {
            throw new RegraDeNegocioException('Você não tem permissão para esta ação.', [], 403);
        }

        if ($usuario->papel === Usuario::MASTER) {
            // o master só muda nome, e-mail e senha: papel, grupo e situação ficam como estão
            $request->merge(['papel' => Usuario::ADMIN, 'grupo_id' => $usuario->grupo_id, 'ativo' => true]);
        } else {
            if ($request->input('papel') === Usuario::MASTER) {
                $this->falha('papel', 'Só existe um master.');
            }
            if ($ator->papel !== Usuario::MASTER) {
                $request->merge(['papel' => $usuario->papel]); // admin não promove nem rebaixa
            }
        }

        $d = $request->validate($this->regras($request, $usuario, false));
        $dados = ['nome' => trim($d['nome']), 'email' => $d['email']];

        if ($usuario->papel !== Usuario::MASTER) {
            $this->conferirGrupo((int) $d['grupo_id']);
            if ($usuario->id === $ator->id && (! $d['ativo'] || $d['papel'] !== $usuario->papel)) {
                throw new RegraDeNegocioException('Você não pode desativar ou rebaixar a si mesmo.', [], 422);
            }
            $dados += ['papel' => $d['papel'], 'grupo_id' => $d['grupo_id'], 'ativo' => $d['ativo']];
        }

        $trocouSenha = ! empty($d['senha']);
        if ($trocouSenha) {
            $dados['senha'] = Hash::make($d['senha']);
        }
        $usuario->update($dados);

        // desativar ou trocar a senha derruba as sessões abertas dessa pessoa
        if ($trocouSenha || ! $usuario->ativo) {
            $usuario->tokens()->when($usuario->id === $ator->id, fn ($q) => $q->where('id', '!=', $request->attributes->get('token_acesso')->id))->delete();
        }

        return $usuario->load('grupo')->paraApi();
    }

    public function destroy(Request $request, Usuario $usuario)
    {
        $ator = $this->ator($request);

        if ($usuario->id === $ator->id || $usuario->papel === Usuario::MASTER) {
            throw new RegraDeNegocioException('Esta conta não pode ser excluída.', [], 422);
        }
        if (! Acesso::podeGerenciar($ator, $usuario)) {
            throw new RegraDeNegocioException('Você não tem permissão para esta ação.', [], 403);
        }
        $usuario->delete();

        return response()->noContent();
    }
}
