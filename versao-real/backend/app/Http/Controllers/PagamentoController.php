<?php

namespace App\Http\Controllers;

use App\Models\Pagamento;
use App\Services\FinanceiroService;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class PagamentoController extends Controller
{
    public function __construct(private FinanceiroService $servico)
    {
    }

    /** Filtro `status`: pendente (a vencer), atrasado, pago ou cancelado. */
    public function index(Request $request)
    {
        $hoje = now()->toDateString();

        return Pagamento::with('orcamento.cliente')
            ->when($request->query('status') === 'pendente', fn ($q) => $q->where('status', Pagamento::PENDENTE)->where('vencimento', '>=', $hoje))
            ->when($request->query('status') === 'atrasado', fn ($q) => $q->where('status', Pagamento::PENDENTE)->where('vencimento', '<', $hoje))
            ->when(in_array($request->query('status'), [Pagamento::PAGO, Pagamento::CANCELADO], true), fn ($q) => $q->where('status', $request->query('status')))
            ->orderByDesc('vencimento')
            ->orderByDesc('id')
            ->get();
    }

    public function baixar(Request $request, Pagamento $pagamento): Pagamento
    {
        $dados = $request->validate([
            'pago_em' => 'required|date_format:Y-m-d|before_or_equal:today',
            'forma' => ['required', Rule::in(Pagamento::FORMAS)],
        ]);

        return $this->servico->baixar($pagamento, $dados['pago_em'], $dados['forma']);
    }
}
