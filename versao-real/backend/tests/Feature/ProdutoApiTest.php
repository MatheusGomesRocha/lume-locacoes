<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class ProdutoApiTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    private function dados(array $extra = []): array
    {
        return array_merge(['codigo' => 'LUZ-900', 'nome' => 'Refletor', 'categoria' => 'Iluminação', 'valor_diaria' => 85, 'quantidade' => 10], $extra);
    }

    public function test_lista_ordenada_por_codigo_e_filtra(): void
    {
        $this->produto(['codigo' => 'B-1', 'nome' => 'Caixa de som', 'categoria' => 'Som']);
        $this->produto(['codigo' => 'A-1', 'nome' => 'Refletor', 'categoria' => 'Luz', 'ativo' => false]);

        $this->getJson('/api/produtos')->assertJsonPath('0.codigo', 'A-1');
        $this->getJson('/api/produtos?q=caixa')->assertJsonCount(1)->assertJsonPath('0.codigo', 'B-1');
        $this->getJson('/api/produtos?q=A-1')->assertJsonCount(1);
        $this->getJson('/api/produtos?categoria=Som')->assertJsonCount(1);
        $this->getJson('/api/produtos?ativo=true')->assertJsonCount(1)->assertJsonPath('0.codigo', 'B-1');
        $this->getJson('/api/produtos?ativo=false')->assertJsonCount(1)->assertJsonPath('0.codigo', 'A-1');
    }

    public function test_cria_produto_com_padroes(): void
    {
        $this->postJson('/api/produtos', $this->dados())
            ->assertCreated()
            ->assertJsonPath('ativo', true)
            ->assertJsonPath('valor_reposicao', 0)
            ->assertJsonPath('valor_diaria', 85);
    }

    public function test_valida_codigo_unico_e_numeros(): void
    {
        $this->produto(['codigo' => 'LUZ-900']);

        $this->postJson('/api/produtos', $this->dados())->assertJsonValidationErrors(['codigo']);
        $this->postJson('/api/produtos', $this->dados(['codigo' => 'X', 'valor_diaria' => -1]))->assertJsonValidationErrors(['valor_diaria']);
        $this->postJson('/api/produtos', $this->dados(['codigo' => 'X', 'quantidade' => 1.5]))->assertJsonValidationErrors(['quantidade']);
        $this->postJson('/api/produtos', [])->assertJsonValidationErrors(['codigo', 'nome', 'categoria', 'valor_diaria', 'quantidade']);
    }

    public function test_atualiza_mantendo_o_proprio_codigo_mas_nao_aceita_o_de_outro(): void
    {
        $a = $this->produto(['codigo' => 'A-1']);
        $this->produto(['codigo' => 'B-1']);

        $this->putJson("/api/produtos/{$a->id}", $this->dados(['codigo' => 'A-1', 'nome' => 'Novo nome']))
            ->assertOk()->assertJsonPath('nome', 'Novo nome');
        $this->putJson("/api/produtos/{$a->id}", $this->dados(['codigo' => 'B-1']))->assertJsonValidationErrors(['codigo']);
    }

    public function test_inativar_pelo_update(): void
    {
        $p = $this->produto();

        $this->putJson("/api/produtos/{$p->id}", $this->dados(['codigo' => $p->codigo, 'ativo' => false]))->assertJsonPath('ativo', false);
    }

    public function test_mostra_e_404(): void
    {
        $p = $this->produto();

        $this->getJson("/api/produtos/{$p->id}")->assertOk()->assertJsonPath('codigo', $p->codigo);
        $this->getJson('/api/produtos/9999')->assertNotFound();
    }

    public function test_exclui_produto_sem_uso(): void
    {
        $p = $this->produto();

        $this->deleteJson("/api/produtos/{$p->id}")->assertNoContent();
        $this->assertDatabaseMissing('produtos', ['id' => $p->id]);
    }

    public function test_nao_exclui_produto_usado_em_orcamento(): void
    {
        $p = $this->produto();
        $this->orcamento(itens: [[$p, 1]]);

        $this->deleteJson("/api/produtos/{$p->id}")->assertStatus(409)->assertJsonPath('message', fn ($m) => str_contains($m, 'Desmarque "Ativo"'));
    }
}
