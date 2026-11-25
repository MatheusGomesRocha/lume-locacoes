<?php

namespace App\Http\Controllers;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Produto;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class ProdutoController extends Controller
{
    private function regras(?Produto $produto = null): array
    {
        return [
            'codigo' => ['required', 'string', 'max:30', Rule::unique('produtos', 'codigo')->ignore($produto?->id)],
            'nome' => 'required|string|max:150',
            'categoria' => 'required|string|max:60',
            'descricao' => 'nullable|string|max:1000',
            'valor_diaria' => 'required|numeric|min:0',
            'valor_reposicao' => 'nullable|numeric|min:0',
            'quantidade' => 'required|integer|min:0',
            'ativo' => 'nullable|boolean',
        ];
    }

    public function index(Request $request)
    {
        $busca = trim((string) $request->query('q', ''));

        return Produto::query()
            ->when($busca !== '', fn ($q) => $q->where(fn ($w) => $w->where('nome', 'like', "%$busca%")->orWhere('codigo', 'like', "%$busca%")))
            ->when($request->filled('categoria'), fn ($q) => $q->where('categoria', $request->query('categoria')))
            ->when($request->filled('ativo'), fn ($q) => $q->where('ativo', filter_var($request->query('ativo'), FILTER_VALIDATE_BOOLEAN)))
            ->orderBy('codigo')
            ->get();
    }

    public function store(Request $request): JsonResponse
    {
        $dados = $request->validate($this->regras());
        $dados['valor_reposicao'] = $dados['valor_reposicao'] ?? 0;
        $dados['ativo'] = $dados['ativo'] ?? true;

        return response()->json(Produto::create($dados), 201);
    }

    public function show(Produto $produto): Produto
    {
        return $produto;
    }

    public function update(Request $request, Produto $produto): Produto
    {
        $dados = $request->validate($this->regras($produto));
        $dados['valor_reposicao'] = $dados['valor_reposicao'] ?? 0;
        $dados['ativo'] = $dados['ativo'] ?? $produto->ativo;
        $produto->update($dados);

        return $produto;
    }

    public function destroy(Produto $produto)
    {
        if ($produto->itens()->exists()) {
            throw new RegraDeNegocioException('Este produto já foi usado em orçamentos e não pode ser excluído. Desmarque "Ativo" para tirá-lo de circulação.', [], 409);
        }

        $produto->delete();

        return response()->noContent();
    }
}
