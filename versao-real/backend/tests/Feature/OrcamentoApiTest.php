<?php

namespace Tests\Feature;

use App\Models\Orcamento;
use App\Models\Pagamento;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class OrcamentoApiTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    private function payload(array $extra = []): array
    {
        $a = $this->produto(['valor_diaria' => 100]);
        $b = $this->produto(['valor_diaria' => 50]);

        return array_merge([
            'cliente_id' => $this->cliente()->id,
            'evento' => 'Casamento',
            'data_retirada' => '2026-12-10',
            'data_devolucao' => '2026-12-12',
            'desconto' => 100,
            'itens' => [['produto_id' => $a->id, 'quantidade' => 2], ['produto_id' => $b->id, 'quantidade' => 4]],
        ], $extra);
    }

    // ---------- criar ----------
    public function test_cria_orcamento_calculando_diarias_total_e_numero(): void
    {
        $r = $this->postJson('/api/orcamentos', $this->payload())->assertCreated();

        // (2×100 + 4×50) × 2 diárias − 100 de desconto
        $r->assertJsonPath('total', 700)
            ->assertJsonPath('diarias', 2)
            ->assertJsonPath('status', 'rascunho')
            ->assertJsonCount(2, 'itens')
            ->assertJsonPath('itens.0.valor_diaria', 100)
            ->assertJsonPath('cliente.nome', 'Cliente Teste');
        $this->assertMatchesRegularExpression('/^\d{4}\/0001$/', $r->json('numero'));
    }

    public function test_numeros_sao_sequenciais(): void
    {
        $this->postJson('/api/orcamentos', $this->payload())->assertCreated();
        $segundo = $this->postJson('/api/orcamentos', $this->payload())->assertCreated();

        $this->assertStringEndsWith('/0002', $segundo->json('numero'));
    }

    public function test_valida_a_criacao(): void
    {
        $this->postJson('/api/orcamentos', [])->assertStatus(422)->assertJsonValidationErrors(['cliente_id', 'evento', 'data_retirada', 'data_devolucao', 'itens']);
        $this->postJson('/api/orcamentos', $this->payload(['itens' => []]))->assertJsonValidationErrors(['itens']);
        $this->postJson('/api/orcamentos', $this->payload(['cliente_id' => 999]))->assertJsonValidationErrors(['cliente_id']);
        $this->postJson('/api/orcamentos', $this->payload(['data_devolucao' => '2026-12-01']))->assertJsonValidationErrors(['data_devolucao']);
        $this->postJson('/api/orcamentos', $this->payload(['data_retirada' => '10/12/2026']))->assertJsonValidationErrors(['data_retirada']);
        $this->postJson('/api/orcamentos', $this->payload(['desconto' => -5]))->assertJsonValidationErrors(['desconto']);
    }

    public function test_valida_os_itens(): void
    {
        $inativo = $this->produto(['ativo' => false]);
        $ativo = $this->produto();

        $this->postJson('/api/orcamentos', $this->payload(['itens' => [['produto_id' => $inativo->id, 'quantidade' => 1]]]))->assertJsonValidationErrors(['itens.0.produto_id']);
        $this->postJson('/api/orcamentos', $this->payload(['itens' => [['produto_id' => $ativo->id, 'quantidade' => 0]]]))->assertJsonValidationErrors(['itens.0.quantidade']);
        $this->postJson('/api/orcamentos', $this->payload(['itens' => [['produto_id' => $ativo->id, 'quantidade' => 1], ['produto_id' => $ativo->id, 'quantidade' => 2]]]))->assertJsonValidationErrors(['itens.0.produto_id']);
    }

    // ---------- leitura ----------
    public function test_lista_com_filtros_de_status_e_busca(): void
    {
        $maria = $this->cliente(['nome' => 'Maria Souza']);
        $this->orcamento('rascunho', dados: ['cliente_id' => $maria->id, 'numero' => '2026/0001', 'evento' => 'Formatura']);
        $this->orcamento('aprovado', dados: ['numero' => '2026/0002', 'evento' => 'Casamento']);

        $this->getJson('/api/orcamentos')->assertJsonCount(2)->assertJsonPath('0.numero', '2026/0002');
        $this->getJson('/api/orcamentos?status=aprovado')->assertJsonCount(1)->assertJsonPath('0.numero', '2026/0002');
        $this->getJson('/api/orcamentos?q=formatura')->assertJsonCount(1);
        $this->getJson('/api/orcamentos?q=maria')->assertJsonCount(1)->assertJsonPath('0.numero', '2026/0001');
        $this->getJson('/api/orcamentos?q=2026/0002')->assertJsonCount(1);
    }

    public function test_mostra_com_itens_cliente_e_pagamentos(): void
    {
        $produto = $this->produto(['nome' => 'Cadeira']);
        $o = $this->orcamento(itens: [[$produto, 3]]);

        $this->getJson("/api/orcamentos/{$o->id}")
            ->assertOk()->assertJsonPath('itens.0.produto.nome', 'Cadeira')->assertJsonStructure(['cliente', 'pagamentos', 'diarias']);
        $this->getJson('/api/orcamentos/9999')->assertNotFound();
    }

    // ---------- editar ----------
    public function test_edita_orcamento_em_rascunho_e_recalcula(): void
    {
        $o = $this->orcamento(itens: [[$this->produto(['valor_diaria' => 100]), 1]]);
        $payload = $this->payload(['desconto' => 0, 'data_devolucao' => '2026-12-10']);

        // 2×100 + 4×50 = 400 em 1 diária
        $this->putJson("/api/orcamentos/{$o->id}", $payload)->assertOk()->assertJsonPath('total', 400)->assertJsonPath('diarias', 1)->assertJsonCount(2, 'itens');
    }

    public function test_edita_orcamento_enviado(): void
    {
        $o = $this->orcamento('enviado');

        $this->putJson("/api/orcamentos/{$o->id}", $this->payload())->assertOk();
    }

    public function test_nao_edita_orcamento_aprovado(): void
    {
        $o = $this->orcamento('aprovado');

        $this->putJson("/api/orcamentos/{$o->id}", $this->payload())
            ->assertStatus(409)->assertJsonPath('message', 'Só é possível editar orçamentos em rascunho ou enviados.');
    }

    public function test_preco_do_item_fica_congelado_mas_item_novo_usa_o_preco_atual(): void
    {
        $antigo = $this->produto(['valor_diaria' => 100]);
        $novo = $this->produto(['valor_diaria' => 50]);
        $criado = $this->postJson('/api/orcamentos', $this->payload([
            'itens' => [['produto_id' => $antigo->id, 'quantidade' => 1]], 'desconto' => 0, 'data_devolucao' => '2026-12-10',
        ]))->assertCreated();

        $antigo->update(['valor_diaria' => 999]);
        $novo->update(['valor_diaria' => 70]);

        $this->getJson('/api/orcamentos/' . $criado->json('id'))->assertJsonPath('itens.0.valor_diaria', 100);

        $this->putJson('/api/orcamentos/' . $criado->json('id'), $this->payload([
            'itens' => [['produto_id' => $antigo->id, 'quantidade' => 1], ['produto_id' => $novo->id, 'quantidade' => 1]],
            'desconto' => 0, 'data_devolucao' => '2026-12-10',
        ]))->assertOk()->assertJsonPath('total', 170); // 100 (congelado) + 70 (preço atual)
    }

    // ---------- enviar ----------
    public function test_envia_orcamento_em_rascunho(): void
    {
        $o = $this->orcamento();

        $this->postJson("/api/orcamentos/{$o->id}/enviar")->assertOk()->assertJsonPath('status', 'enviado');
        $this->postJson("/api/orcamentos/{$o->id}/enviar")->assertStatus(409);
    }

    // ---------- aprovar ----------
    public function test_aprova_e_cria_a_cobranca_com_vencimento_na_retirada(): void
    {
        $produto = $this->produto(['valor_diaria' => 100, 'quantidade' => 5]);
        $o = $this->orcamento('enviado', '2026-12-10', '2026-12-12', [[$produto, 2]]);

        $this->postJson("/api/orcamentos/{$o->id}/aprovar")
            ->assertOk()
            ->assertJsonPath('status', 'aprovado')
            ->assertJsonCount(1, 'pagamentos')
            ->assertJsonPath('pagamentos.0.valor', 400)
            ->assertJsonPath('pagamentos.0.vencimento', '2026-12-10')
            ->assertJsonPath('pagamentos.0.status', 'pendente');
    }

    public function test_aprova_orcamento_em_rascunho(): void
    {
        $o = $this->orcamento('rascunho', itens: [[$this->produto(), 1]]);

        $this->postJson("/api/orcamentos/{$o->id}/aprovar")->assertOk()->assertJsonPath('status', 'aprovado');
    }

    public function test_nao_aprova_duas_vezes_nem_orcamento_cancelado(): void
    {
        $o = $this->orcamento('rascunho', itens: [[$this->produto(), 1]]);
        $this->postJson("/api/orcamentos/{$o->id}/aprovar")->assertOk();
        $this->postJson("/api/orcamentos/{$o->id}/aprovar")->assertStatus(409);

        $cancelado = $this->orcamento('cancelado');
        $this->postJson("/api/orcamentos/{$cancelado->id}/aprovar")->assertStatus(409);
        $this->assertSame(1, Pagamento::count());
    }

    public function test_nao_aprova_sem_estoque_e_informa_o_que_falta(): void
    {
        $produto = $this->produto(['quantidade' => 5, 'codigo' => 'LUZ-1', 'nome' => 'Refletor']);
        $this->orcamento('aprovado', '2026-12-10', '2026-12-12', [[$produto, 4]]);
        $novo = $this->orcamento('rascunho', '2026-12-11', '2026-12-13', [[$produto, 2]]);

        $this->postJson("/api/orcamentos/{$novo->id}/aprovar")
            ->assertStatus(422)
            ->assertJsonPath('message', 'Não há estoque suficiente para o período do orçamento.')
            ->assertJsonPath('detalhes.0.codigo', 'LUZ-1')
            ->assertJsonPath('detalhes.0.solicitado', 2)
            ->assertJsonPath('detalhes.0.disponivel', 1);

        $this->assertSame('rascunho', $novo->fresh()->status);
        $this->assertSame(0, $novo->pagamentos()->count());
    }

    public function test_aprova_quando_os_periodos_nao_se_sobrepoem(): void
    {
        $produto = $this->produto(['quantidade' => 5]);
        $this->orcamento('aprovado', '2026-12-01', '2026-12-05', [[$produto, 5]]);
        $novo = $this->orcamento('rascunho', '2026-12-06', '2026-12-08', [[$produto, 5]]);

        $this->postJson("/api/orcamentos/{$novo->id}/aprovar")->assertOk();
    }

    // ---------- finalizar ----------
    public function test_finaliza_apenas_orcamento_aprovado(): void
    {
        $aprovado = $this->orcamento('aprovado');
        $rascunho = $this->orcamento('rascunho');

        $this->postJson("/api/orcamentos/{$aprovado->id}/finalizar")->assertOk()->assertJsonPath('status', 'finalizado');
        $this->postJson("/api/orcamentos/{$rascunho->id}/finalizar")->assertStatus(409);
    }

    public function test_finalizado_deixa_de_segurar_estoque(): void
    {
        $produto = $this->produto(['quantidade' => 3]);
        $a = $this->orcamento('aprovado', '2026-12-10', '2026-12-12', [[$produto, 3]]);
        $b = $this->orcamento('rascunho', '2026-12-10', '2026-12-12', [[$produto, 3]]);
        $this->postJson("/api/orcamentos/{$b->id}/aprovar")->assertStatus(422);

        $this->postJson("/api/orcamentos/{$a->id}/finalizar")->assertOk();
        $this->postJson("/api/orcamentos/{$b->id}/aprovar")->assertOk();
    }

    // ---------- cancelar ----------
    public function test_cancela_orcamento_aprovado_e_suas_cobrancas_pendentes(): void
    {
        $o = $this->orcamento('aprovado');
        $pendente = $this->pagamento($o);
        $paga = $this->pagamento($o, 'pago', '2026-12-01', '2026-12-02');

        $this->postJson("/api/orcamentos/{$o->id}/cancelar")->assertOk()->assertJsonPath('status', 'cancelado');

        $this->assertSame('cancelado', $pendente->fresh()->status);
        $this->assertSame('pago', $paga->fresh()->status);
    }

    public function test_cancelar_libera_o_estoque(): void
    {
        $produto = $this->produto(['quantidade' => 2]);
        $a = $this->orcamento('aprovado', '2026-12-10', '2026-12-12', [[$produto, 2]]);
        $b = $this->orcamento('rascunho', '2026-12-10', '2026-12-12', [[$produto, 2]]);

        $this->postJson("/api/orcamentos/{$b->id}/aprovar")->assertStatus(422);
        $this->postJson("/api/orcamentos/{$a->id}/cancelar")->assertOk();
        $this->postJson("/api/orcamentos/{$b->id}/aprovar")->assertOk();
    }

    public function test_nao_cancela_finalizado_nem_cancelado(): void
    {
        $finalizado = $this->orcamento('finalizado');
        $cancelado = $this->orcamento('cancelado');

        $this->postJson("/api/orcamentos/{$finalizado->id}/cancelar")->assertStatus(409);
        $this->postJson("/api/orcamentos/{$cancelado->id}/cancelar")->assertStatus(409);
    }

    // ---------- excluir ----------
    public function test_exclui_rascunho_e_cancelado_com_seus_itens(): void
    {
        $rascunho = $this->orcamento('rascunho', itens: [[$this->produto(), 1]]);
        $cancelado = $this->orcamento('cancelado');

        $this->deleteJson("/api/orcamentos/{$rascunho->id}")->assertNoContent();
        $this->deleteJson("/api/orcamentos/{$cancelado->id}")->assertNoContent();

        $this->assertSame(0, Orcamento::count());
        $this->assertDatabaseCount('orcamento_itens', 0);
    }

    public function test_nao_exclui_orcamento_enviado_aprovado_ou_finalizado(): void
    {
        foreach (['enviado', 'aprovado', 'finalizado'] as $status) {
            $o = $this->orcamento($status);
            $this->deleteJson("/api/orcamentos/{$o->id}")->assertStatus(409);
        }
        $this->assertSame(3, Orcamento::count());
    }
}
