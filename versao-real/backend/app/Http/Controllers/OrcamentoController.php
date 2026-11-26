<?php

namespace App\Http\Controllers;

use App\Models\Orcamento;
use App\Services\OrcamentoService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class OrcamentoController extends Controller
{
    public function __construct(private OrcamentoService $servico)
    {
    }

    private function regras(): array
    {
        return [
            'cliente_id' => 'required|integer|exists:clientes,id',
            'evento' => 'required|string|max:150',
            'data_retirada' => 'required|date_format:Y-m-d',
            'data_devolucao' => 'required|date_format:Y-m-d|after_or_equal:data_retirada',
            'desconto' => 'nullable|numeric|min:0',
            'observacoes' => 'nullable|string|max:2000',
            'itens' => 'required|array|min:1',
            'itens.*.produto_id' => ['required', 'integer', 'distinct', Rule::exists('produtos', 'id')->where('ativo', true)],
            'itens.*.quantidade' => 'required|integer|min:1',
        ];
    }

    public function index(Request $request)
    {
        $busca = trim((string) $request->query('q', ''));

        $consulta = Orcamento::with(['cliente', 'itens.produto', 'pagamentos'])
            ->when($request->filled('status'), fn ($q) => $q->where('status', $request->query('status')))
            ->when($busca !== '', fn ($q) => $q->where(fn ($w) => $w
                ->where('numero', 'like', "%$busca%")
                ->orWhere('evento', 'like', "%$busca%")
                ->orWhereHas('cliente', fn ($c) => $c->where('nome', 'like', "%$busca%"))))
            ->orderByDesc('id');

        return $this->listaPaginada($request, $consulta);
    }

    public function store(Request $request): JsonResponse
    {
        return response()->json($this->servico->criar($request->validate($this->regras())), 201);
    }

    public function show(Orcamento $orcamento): Orcamento
    {
        return $this->servico->carregar($orcamento);
    }

    public function update(Request $request, Orcamento $orcamento): Orcamento
    {
        return $this->servico->atualizar($orcamento, $request->validate($this->regras()));
    }

    public function destroy(Orcamento $orcamento)
    {
        $this->servico->excluir($orcamento);

        return response()->noContent();
    }

    public function enviar(Orcamento $orcamento): Orcamento
    {
        return $this->servico->enviar($orcamento);
    }

    public function aprovar(Orcamento $orcamento): Orcamento
    {
        return $this->servico->aprovar($orcamento);
    }

    public function finalizar(Orcamento $orcamento): Orcamento
    {
        return $this->servico->finalizar($orcamento);
    }

    public function cancelar(Orcamento $orcamento): Orcamento
    {
        return $this->servico->cancelar($orcamento);
    }
}
