<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class PagamentoApiTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    private function cenario(): array
    {
        $o = $this->orcamento('aprovado');

        return [
            'avencer' => $this->pagamento($o, 'pendente', $this->hoje('+5 days')),
            'hoje' => $this->pagamento($o, 'pendente', $this->hoje()),
            'atrasado' => $this->pagamento($o, 'pendente', $this->hoje('-3 days')),
            'pago' => $this->pagamento($o, 'pago', $this->hoje('-10 days'), $this->hoje('-9 days')),
            'cancelado' => $this->pagamento($o, 'cancelado', $this->hoje('-1 days')),
        ];
    }

    public function test_lista_todos_com_orcamento_e_cliente_do_mais_recente_ao_mais_antigo(): void
    {
        $this->cenario();

        $this->getJson('/api/pagamentos')->assertOk()->assertJsonCount(5)
            ->assertJsonPath('0.vencimento', $this->hoje('+5 days'))
            ->assertJsonStructure([['id', 'valor', 'vencimento', 'status', 'orcamento' => ['numero', 'cliente' => ['nome']]]]);
    }

    public function test_filtra_pendentes_a_vencer_incluindo_o_que_vence_hoje(): void
    {
        $c = $this->cenario();

        $ids = collect($this->getJson('/api/pagamentos?status=pendente')->json())->pluck('id')->all();

        $this->assertEqualsCanonicalizing([$c['avencer']->id, $c['hoje']->id], $ids);
    }

    public function test_filtra_atrasados_pagos_e_cancelados(): void
    {
        $c = $this->cenario();

        $this->getJson('/api/pagamentos?status=atrasado')->assertJsonCount(1)->assertJsonPath('0.id', $c['atrasado']->id);
        $this->getJson('/api/pagamentos?status=pago')->assertJsonCount(1)->assertJsonPath('0.id', $c['pago']->id);
        $this->getJson('/api/pagamentos?status=cancelado')->assertJsonCount(1)->assertJsonPath('0.id', $c['cancelado']->id);
    }

    public function test_baixa_registra_data_forma_e_status(): void
    {
        $p = $this->pagamento($this->orcamento('aprovado'), 'pendente', $this->hoje('-2 days'));

        $this->postJson("/api/pagamentos/{$p->id}/baixar", ['pago_em' => $this->hoje(), 'forma' => 'pix'])
            ->assertOk()->assertJsonPath('status', 'pago')->assertJsonPath('forma', 'pix')->assertJsonPath('pago_em', $this->hoje());
    }

    public function test_baixa_valida_dados(): void
    {
        $p = $this->pagamento($this->orcamento('aprovado'));

        $this->postJson("/api/pagamentos/{$p->id}/baixar", [])->assertStatus(422)->assertJsonValidationErrors(['pago_em', 'forma']);
        $this->postJson("/api/pagamentos/{$p->id}/baixar", ['pago_em' => $this->hoje(), 'forma' => 'cheque'])->assertJsonValidationErrors(['forma']);
        $this->postJson("/api/pagamentos/{$p->id}/baixar", ['pago_em' => $this->hoje('+2 days'), 'forma' => 'pix'])->assertJsonValidationErrors(['pago_em']);
    }

    public function test_nao_da_baixa_em_pago_nem_em_cancelado(): void
    {
        $c = $this->cenario();

        $this->postJson("/api/pagamentos/{$c['pago']->id}/baixar", ['pago_em' => $this->hoje(), 'forma' => 'pix'])->assertStatus(409);
        $this->postJson("/api/pagamentos/{$c['cancelado']->id}/baixar", ['pago_em' => $this->hoje(), 'forma' => 'pix'])->assertStatus(409);
    }

    public function test_baixa_de_pagamento_inexistente_da_404(): void
    {
        $this->postJson('/api/pagamentos/999/baixar', ['pago_em' => $this->hoje(), 'forma' => 'pix'])->assertNotFound();
    }
}
