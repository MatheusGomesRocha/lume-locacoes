<?php

namespace Tests\Feature;

use App\Models\Cliente;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class ClienteApiTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    public function test_lista_clientes_em_ordem_alfabetica(): void
    {
        $this->cliente(['nome' => 'Zélia']);
        $this->cliente(['nome' => 'Ana']);

        $this->getJson('/api/clientes')->assertOk()->assertJsonPath('0.nome', 'Ana')->assertJsonPath('1.nome', 'Zélia');
    }

    public function test_lista_paginada_traz_o_total_e_so_a_pagina_pedida(): void
    {
        foreach (range(1, 12) as $i) {
            $this->cliente(['nome' => sprintf('Cliente %02d', $i)]);
        }

        $this->getJson('/api/clientes?por_pagina=10&pagina=1')->assertOk()
            ->assertJsonCount(10, 'dados')->assertJsonPath('total', 12)->assertJsonPath('ultima_pagina', 2)->assertJsonPath('dados.0.nome', 'Cliente 01');
        $this->getJson('/api/clientes?por_pagina=10&pagina=2')->assertJsonCount(2, 'dados')->assertJsonPath('dados.0.nome', 'Cliente 11');
        $this->getJson('/api/clientes?por_pagina=5000')->assertJsonPath('por_pagina', 100); // o servidor limita
        $this->getJson('/api/clientes')->assertJsonCount(12); // sem por_pagina, a lista inteira de sempre
    }

    public function test_busca_por_nome_documento_email_e_cidade(): void
    {
        $this->cliente(['nome' => 'Buffet Sabor', 'documento' => '12.345', 'cidade' => 'Aquiraz']);
        $this->cliente(['nome' => 'Outro', 'email' => 'x@example.com']);

        $this->getJson('/api/clientes?q=sabor')->assertJsonCount(1);
        $this->getJson('/api/clientes?q=12.345')->assertJsonCount(1);
        $this->getJson('/api/clientes?q=aquiraz')->assertJsonCount(1);
        $this->getJson('/api/clientes?q=x@example')->assertJsonCount(1);
        $this->getJson('/api/clientes?q=nada')->assertJsonCount(0);
    }

    public function test_cria_cliente(): void
    {
        $this->postJson('/api/clientes', ['nome' => 'Maria', 'tipo' => 'PF', 'cidade' => 'Fortaleza'])
            ->assertCreated()
            ->assertJsonPath('nome', 'Maria');

        $this->assertDatabaseHas('clientes', ['nome' => 'Maria', 'cidade' => 'Fortaleza']);
    }

    public function test_valida_campos_obrigatorios_e_formatos(): void
    {
        $this->postJson('/api/clientes', [])->assertStatus(422)->assertJsonValidationErrors(['nome', 'tipo']);
        $this->postJson('/api/clientes', ['nome' => 'A', 'tipo' => 'XX'])->assertJsonValidationErrors(['tipo']);
        $this->postJson('/api/clientes', ['nome' => 'A', 'tipo' => 'PF', 'email' => 'invalido'])->assertJsonValidationErrors(['email']);
    }

    public function test_mensagens_de_validacao_saem_em_portugues(): void
    {
        $this->postJson('/api/clientes', [])->assertJsonPath('errors.nome.0', 'O campo nome é obrigatório.');
    }

    public function test_mostra_um_cliente_e_devolve_404_para_inexistente(): void
    {
        $cliente = $this->cliente(['nome' => 'João']);

        $this->getJson("/api/clientes/{$cliente->id}")->assertOk()->assertJsonPath('nome', 'João');
        $this->getJson('/api/clientes/9999')->assertNotFound();
    }

    public function test_atualiza_cliente(): void
    {
        $cliente = $this->cliente(['nome' => 'João']);

        $this->putJson("/api/clientes/{$cliente->id}", ['nome' => 'João Silva', 'tipo' => 'PJ'])
            ->assertOk()->assertJsonPath('nome', 'João Silva')->assertJsonPath('tipo', 'PJ');
    }

    public function test_exclui_cliente_sem_orcamentos(): void
    {
        $cliente = $this->cliente();

        $this->deleteJson("/api/clientes/{$cliente->id}")->assertNoContent();
        $this->assertDatabaseMissing('clientes', ['id' => $cliente->id]);
    }

    public function test_nao_exclui_cliente_que_tem_orcamentos(): void
    {
        $cliente = $this->cliente();
        $this->orcamento(dados: ['cliente_id' => $cliente->id]);

        $this->deleteJson("/api/clientes/{$cliente->id}")
            ->assertStatus(409)
            ->assertJsonPath('message', 'Este cliente já tem orçamentos e não pode ser excluído.');
        $this->assertTrue(Cliente::whereKey($cliente->id)->exists());
    }
}
