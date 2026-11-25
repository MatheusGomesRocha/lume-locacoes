<?php

namespace Tests\Concerns;

use App\Models\Cliente;
use App\Models\Orcamento;
use App\Models\Pagamento;
use App\Models\Produto;
use App\Services\OrcamentoService;
use Illuminate\Support\Carbon;

/** Atalhos para montar cenários nos testes sem repetir código. */
trait CriaDados
{
    private int $contador = 0;

    protected function cliente(array $dados = []): Cliente
    {
        return Cliente::create(array_merge(['nome' => 'Cliente Teste', 'tipo' => 'PF'], $dados));
    }

    protected function produto(array $dados = []): Produto
    {
        $n = ++$this->contador;

        return Produto::create(array_merge([
            'codigo' => "T-$n", 'nome' => "Produto $n", 'categoria' => 'Teste',
            'valor_diaria' => 100, 'valor_reposicao' => 500, 'quantidade' => 10, 'ativo' => true,
        ], $dados));
    }

    /**
     * Cria um orçamento direto no banco (sem passar pelas regras da API).
     *
     * @param  array<int, array{0: Produto, 1: int}>  $itens  pares [produto, quantidade]
     */
    protected function orcamento(string $status = 'rascunho', string $retirada = '2026-12-10', string $devolucao = '2026-12-12', array $itens = [], array $dados = []): Orcamento
    {
        $n = ++$this->contador;
        $linhas = array_map(fn ($par) => ['produto_id' => $par[0]->id, 'quantidade' => $par[1], 'valor_diaria' => $par[0]->valor_diaria], $itens);
        $desconto = (float) ($dados['desconto'] ?? 0);

        $orcamento = Orcamento::create(array_merge([
            'numero' => sprintf('2026/%04d', 900 + $n),
            'cliente_id' => $dados['cliente_id'] ?? $this->cliente()->id,
            'evento' => 'Evento de teste',
            'data_retirada' => $retirada,
            'data_devolucao' => $devolucao,
            'status' => $status,
            'desconto' => $desconto,
            'total' => OrcamentoService::calcularTotal($linhas, OrcamentoService::diarias($retirada, $devolucao), $desconto),
        ], $dados));
        $orcamento->itens()->createMany($linhas);

        return $orcamento;
    }

    protected function pagamento(Orcamento $orcamento, string $status = 'pendente', string $vencimento = '2026-12-10', ?string $pagoEm = null, float $valor = 100): Pagamento
    {
        return Pagamento::create([
            'orcamento_id' => $orcamento->id, 'valor' => $valor, 'vencimento' => $vencimento,
            'pago_em' => $pagoEm, 'forma' => $pagoEm ? 'pix' : null, 'status' => $status,
        ]);
    }

    protected function hoje(string $deslocamento = '+0 days'): string
    {
        return Carbon::parse($deslocamento)->toDateString();
    }
}
