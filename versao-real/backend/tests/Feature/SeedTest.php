<?php

namespace Tests\Feature;

use App\Models\Cliente;
use App\Models\Orcamento;
use App\Models\Pagamento;
use App\Models\Produto;
use App\Services\OrcamentoService;
use Database\Seeders\DatabaseSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SeedTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->seed(DatabaseSeeder::class);
    }

    public function test_cadastra_os_dados_de_exemplo(): void
    {
        $this->assertSame(14, Cliente::count());
        $this->assertSame(30, Produto::count());
        $this->assertSame(30, Orcamento::count());
        $this->assertSame(19, Pagamento::count());
    }

    public function test_totais_do_orcamento_batem_com_as_regras(): void
    {
        foreach (Orcamento::with('itens')->get() as $o) {
            $esperado = OrcamentoService::calcularTotal($o->itens->all() ? $o->itens->toArray() : [], OrcamentoService::diarias($o->data_retirada, $o->data_devolucao), (float) $o->desconto);
            $this->assertEqualsWithDelta($esperado, (float) $o->total, 0.01, "Total divergente em {$o->numero}");
        }
    }

    public function test_numeros_sao_unicos(): void
    {
        $this->assertSame(30, Orcamento::distinct('numero')->count('numero'));
    }

    public function test_dados_de_exemplo_nao_tem_conflito_de_estoque(): void
    {
        $servico = new OrcamentoService();
        foreach (Orcamento::where('status', 'aprovado')->get() as $o) {
            $this->assertSame([], $servico->faltas($o), "Estoque estourado em {$o->numero}");
        }
    }

    public function test_pagamentos_pagos_tem_data_e_pendentes_nao(): void
    {
        $this->assertSame(0, Pagamento::where('status', 'pago')->whereNull('pago_em')->count());
        $this->assertSame(0, Pagamento::where('status', 'pendente')->whereNotNull('pago_em')->count());
    }

    public function test_painel_funciona_com_os_dados_de_exemplo(): void
    {
        $this->getJson('/api/dashboard')->assertOk()->assertJsonCount(6, 'recebido_por_mes');
    }
}
