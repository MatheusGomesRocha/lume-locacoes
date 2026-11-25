<?php

namespace App\Services;

use App\Exceptions\RegraDeNegocioException;
use App\Models\Orcamento;
use App\Models\OrcamentoItem;
use App\Models\Pagamento;
use App\Models\Produto;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Regras do orçamento: cálculo, numeração, estoque e mudanças de status.
 * Os controllers só validam a entrada e chamam este serviço.
 */
class OrcamentoService
{
    /** Dias entre retirada e devolução, no mínimo 1 (mesmo dia = 1 diária). */
    public static function diarias(?string $retirada, ?string $devolucao): int
    {
        if (! $retirada || ! $devolucao) {
            return 1;
        }

        $dias = Carbon::parse($retirada)->startOfDay()->diffInDays(Carbon::parse($devolucao)->startOfDay(), false);

        return max(1, (int) $dias);
    }

    /**
     * Total = soma(quantidade × valor da diária) × diárias − desconto, nunca negativo.
     *
     * @param  array<int, array{quantidade: int|float, valor_diaria: int|float}>  $itens
     */
    public static function calcularTotal(array $itens, int $diarias, float $desconto = 0): float
    {
        $subtotal = 0.0;
        foreach ($itens as $item) {
            $subtotal += $item['quantidade'] * $item['valor_diaria'];
        }

        return round(max(0, $subtotal * $diarias - $desconto), 2);
    }

    /** Próximo número no formato AAAA/NNNN. A sequência reinicia a cada ano. */
    public static function proximoNumero(?Carbon $hoje = null): string
    {
        $ano = ($hoje ?? now())->year;
        $maior = Orcamento::where('numero', 'like', "$ano/%")
            ->pluck('numero')
            ->map(fn ($numero) => (int) substr($numero, 5))
            ->max() ?? 0;

        return sprintf('%d/%04d', $ano, $maior + 1);
    }

    public function criar(array $dados): Orcamento
    {
        return DB::transaction(function () use ($dados) {
            $itens = $this->montarItens($dados['itens']);
            $desconto = (float) ($dados['desconto'] ?? 0);
            $diarias = self::diarias($dados['data_retirada'], $dados['data_devolucao']);

            $orcamento = Orcamento::create([
                'numero' => self::proximoNumero(),
                'cliente_id' => $dados['cliente_id'],
                'evento' => $dados['evento'],
                'data_retirada' => $dados['data_retirada'],
                'data_devolucao' => $dados['data_devolucao'],
                'status' => Orcamento::RASCUNHO,
                'desconto' => $desconto,
                'total' => self::calcularTotal($itens, $diarias, $desconto),
                'observacoes' => $dados['observacoes'] ?? null,
            ]);
            $orcamento->itens()->createMany($itens);

            return $this->carregar($orcamento);
        });
    }

    public function atualizar(Orcamento $orcamento, array $dados): Orcamento
    {
        $this->exigirStatus($orcamento, [Orcamento::RASCUNHO, Orcamento::ENVIADO], 'Só é possível editar orçamentos em rascunho ou enviados.');

        return DB::transaction(function () use ($orcamento, $dados) {
            // Quem já estava no orçamento mantém o valor combinado; só itens novos pegam o preço atual.
            $valoresAntigos = $orcamento->itens()->pluck('valor_diaria', 'produto_id')->all();
            $itens = $this->montarItens($dados['itens'], $valoresAntigos);
            $desconto = (float) ($dados['desconto'] ?? 0);
            $diarias = self::diarias($dados['data_retirada'], $dados['data_devolucao']);

            $orcamento->update([
                'cliente_id' => $dados['cliente_id'],
                'evento' => $dados['evento'],
                'data_retirada' => $dados['data_retirada'],
                'data_devolucao' => $dados['data_devolucao'],
                'desconto' => $desconto,
                'total' => self::calcularTotal($itens, $diarias, $desconto),
                'observacoes' => $dados['observacoes'] ?? null,
            ]);
            $orcamento->itens()->delete();
            $orcamento->itens()->createMany($itens);

            return $this->carregar($orcamento);
        });
    }

    public function enviar(Orcamento $orcamento): Orcamento
    {
        $this->exigirStatus($orcamento, [Orcamento::RASCUNHO], 'Só orçamentos em rascunho podem ser enviados.');
        $orcamento->update(['status' => Orcamento::ENVIADO]);

        return $this->carregar($orcamento);
    }

    public function aprovar(Orcamento $orcamento): Orcamento
    {
        $this->exigirStatus($orcamento, [Orcamento::RASCUNHO, Orcamento::ENVIADO], 'Só orçamentos em rascunho ou enviados podem ser aprovados.');

        $faltas = $this->faltas($orcamento);
        if ($faltas) {
            throw new RegraDeNegocioException('Não há estoque suficiente para o período do orçamento.', $faltas);
        }

        DB::transaction(function () use ($orcamento) {
            $orcamento->update(['status' => Orcamento::APROVADO]);
            $orcamento->pagamentos()->create([
                'valor' => $orcamento->total,
                'vencimento' => $orcamento->data_retirada,
                'status' => Pagamento::PENDENTE,
            ]);
        });

        return $this->carregar($orcamento);
    }

    public function finalizar(Orcamento $orcamento): Orcamento
    {
        $this->exigirStatus($orcamento, [Orcamento::APROVADO], 'Só orçamentos aprovados podem ser finalizados.');
        $orcamento->update(['status' => Orcamento::FINALIZADO]);

        return $this->carregar($orcamento);
    }

    public function cancelar(Orcamento $orcamento): Orcamento
    {
        $this->exigirStatus($orcamento, [Orcamento::RASCUNHO, Orcamento::ENVIADO, Orcamento::APROVADO], 'Orçamentos finalizados ou já cancelados não podem ser cancelados.');

        DB::transaction(function () use ($orcamento) {
            $orcamento->update(['status' => Orcamento::CANCELADO]);
            $orcamento->pagamentos()->where('status', Pagamento::PENDENTE)->update(['status' => Pagamento::CANCELADO]);
        });

        return $this->carregar($orcamento);
    }

    public function excluir(Orcamento $orcamento): void
    {
        $this->exigirStatus($orcamento, [Orcamento::RASCUNHO, Orcamento::CANCELADO], 'Só orçamentos em rascunho ou cancelados podem ser excluídos.');

        DB::transaction(function () use ($orcamento) {
            $orcamento->itens()->delete();
            $orcamento->pagamentos()->delete();
            $orcamento->delete();
        });
    }

    /**
     * Itens que não cabem no estoque do período. Só orçamentos APROVADOS seguram estoque;
     * finalizados já devolveram os itens e rascunhos ainda não são compromisso.
     *
     * @return array<int, array{produto_id: int, codigo: string, produto: string, solicitado: int, disponivel: int}>
     */
    public function faltas(Orcamento $orcamento): array
    {
        $faltas = [];

        foreach ($orcamento->itens()->with('produto')->get() as $item) {
            $comprometido = (int) OrcamentoItem::where('produto_id', $item->produto_id)
                ->whereHas('orcamento', function ($q) use ($orcamento) {
                    $q->where('status', Orcamento::APROVADO)
                        ->where('id', '!=', $orcamento->id)
                        ->where('data_retirada', '<=', $orcamento->data_devolucao)
                        ->where('data_devolucao', '>=', $orcamento->data_retirada);
                })
                ->sum('quantidade');

            $disponivel = max(0, $item->produto->quantidade - $comprometido);

            if ($item->quantidade > $disponivel) {
                $faltas[] = [
                    'produto_id' => $item->produto_id,
                    'codigo' => $item->produto->codigo,
                    'produto' => $item->produto->nome,
                    'solicitado' => $item->quantidade,
                    'disponivel' => $disponivel,
                ];
            }
        }

        return $faltas;
    }

    public function carregar(Orcamento $orcamento): Orcamento
    {
        return $orcamento->fresh(['cliente', 'itens.produto', 'pagamentos']);
    }

    /**
     * @param  array<int, array{produto_id: int, quantidade: int}>  $entrada
     * @param  array<int, float|string>  $valoresAntigos  produto_id => valor da diária já combinado
     */
    private function montarItens(array $entrada, array $valoresAntigos = []): array
    {
        return array_map(function (array $item) use ($valoresAntigos) {
            $produto = Produto::findOrFail($item['produto_id']);

            return [
                'produto_id' => $produto->id,
                'quantidade' => (int) $item['quantidade'],
                'valor_diaria' => (float) ($valoresAntigos[$produto->id] ?? $produto->valor_diaria),
            ];
        }, array_values($entrada));
    }

    private function exigirStatus(Orcamento $orcamento, array $permitidos, string $mensagem): void
    {
        if (! in_array($orcamento->status, $permitidos, true)) {
            throw new RegraDeNegocioException($mensagem, [], 409);
        }
    }
}
