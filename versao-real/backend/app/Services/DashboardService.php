<?php

namespace App\Services;

use App\Models\Orcamento;
use App\Models\OrcamentoItem;
use App\Models\Pagamento;
use Illuminate\Support\Carbon;

class DashboardService
{
    public function resumo(?Carbon $hoje = null): array
    {
        $hoje = ($hoje ?? now())->copy()->startOfDay();
        $dia = $hoje->toDateString();
        $inicioMes = $hoje->copy()->startOfMonth()->toDateString();
        $fimMes = $hoje->copy()->endOfMonth()->toDateString();

        return [
            'recebido_mes' => $this->soma(Pagamento::where('status', Pagamento::PAGO)->whereBetween('pago_em', [$inicioMes, $fimMes])),
            'a_receber' => $this->soma(Pagamento::where('status', Pagamento::PENDENTE)->where('vencimento', '>=', $dia)),
            'em_atraso' => $this->soma(Pagamento::where('status', Pagamento::PENDENTE)->where('vencimento', '<', $dia)),
            'orcamentos_em_aberto' => Orcamento::whereIn('status', [Orcamento::RASCUNHO, Orcamento::ENVIADO])->count(),
            'recebido_por_mes' => $this->recebidoPorMes($hoje),
            'orcamentos_por_status' => $this->orcamentosPorStatus(),
            'produtos_mais_alugados' => $this->produtosMaisAlugados(),
            'proximos_eventos' => $this->proximosEventos($dia),
        ];
    }

    private function soma($consulta): float
    {
        return round((float) $consulta->sum('valor'), 2);
    }

    /** Últimos 6 meses (o atual incluído), do mais antigo ao mais recente. */
    private function recebidoPorMes(Carbon $hoje): array
    {
        $primeiro = $hoje->copy()->startOfMonth()->subMonths(5);
        $pagos = Pagamento::where('status', Pagamento::PAGO)
            ->where('pago_em', '>=', $primeiro->toDateString())
            ->get(['valor', 'pago_em'])
            ->groupBy(fn ($p) => substr($p->pago_em, 0, 7));

        $meses = [];
        for ($i = 0; $i < 6; $i++) {
            $chave = $primeiro->copy()->addMonths($i)->format('Y-m');
            $meses[] = ['mes' => $chave, 'total' => round((float) ($pagos[$chave] ?? collect())->sum('valor'), 2)];
        }

        return $meses;
    }

    private function orcamentosPorStatus(): array
    {
        $contagens = Orcamento::selectRaw('status, count(*) as total')->groupBy('status')->pluck('total', 'status');

        return collect(Orcamento::STATUS)->map(fn ($s) => ['status' => $s, 'total' => (int) ($contagens[$s] ?? 0)])->all();
    }

    private function produtosMaisAlugados(): array
    {
        return OrcamentoItem::selectRaw('produto_id, SUM(quantidade) as total')
            ->whereHas('orcamento', fn ($q) => $q->whereIn('status', [Orcamento::APROVADO, Orcamento::FINALIZADO]))
            ->groupBy('produto_id')
            ->orderByDesc('total')
            ->orderBy('produto_id')
            ->limit(5)
            ->with('produto:id,codigo,nome')
            ->get()
            ->map(fn ($i) => ['produto_id' => $i->produto_id, 'codigo' => $i->produto->codigo, 'nome' => $i->produto->nome, 'quantidade' => (int) $i->total])
            ->all();
    }

    private function proximosEventos(string $dia): array
    {
        return Orcamento::with('cliente:id,nome')
            ->where('status', Orcamento::APROVADO)
            ->where('data_retirada', '>=', $dia)
            ->orderBy('data_retirada')
            ->orderBy('id')
            ->limit(5)
            ->get()
            ->map(fn ($o) => [
                'id' => $o->id,
                'numero' => $o->numero,
                'evento' => $o->evento,
                'cliente' => $o->cliente->nome,
                'data_retirada' => $o->data_retirada,
                'data_devolucao' => $o->data_devolucao,
                'total' => $o->total,
            ])
            ->all();
    }
}
