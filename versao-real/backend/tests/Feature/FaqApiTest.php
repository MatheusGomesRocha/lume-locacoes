<?php

namespace Tests\Feature;

use App\Models\FaqItem;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/** Respostas do master para as perguntas sem resposta: só o master mexe, nem o administrador com todas as permissões. */
class FaqApiTest extends TestCase
{
    use RefreshDatabase;

    private function dados(array $extra = []): array
    {
        return array_merge(['modulo' => 'Acesso', 'pergunta' => 'Como adicionar uma pessoa ao sistema?', 'resposta' => 'Peça ao master para cadastrar você em Usuários.',
            'palavras_chave' => ['como adiciono uma pessoa no sistema', ' adicionar pessoa ', 'adicionar pessoa', '']], $extra);
    }

    public function test_master_cria_lista_edita_e_exclui(): void
    {
        $id = $this->postJson('/api/faq-itens', $this->dados())->assertCreated()->assertJsonStructure(['id', 'criado_em'])
            ->assertJsonPath('palavras_chave', ['como adiciono uma pessoa no sistema', 'adicionar pessoa'])->json('id');

        $this->getJson('/api/faq-itens')->assertOk()->assertJsonCount(1)->assertJsonPath('0.id', $id);
        $this->putJson("/api/faq-itens/{$id}", $this->dados(['resposta' => 'Nova resposta para a pergunta.']))->assertOk()->assertJsonPath('resposta', 'Nova resposta para a pergunta.');
        $this->deleteJson("/api/faq-itens/{$id}")->assertNoContent();
        $this->assertDatabaseCount('faq_itens', 0);
    }

    public function test_valida_os_campos(): void
    {
        $this->postJson('/api/faq-itens', $this->dados(['modulo' => 'Outro']))->assertUnprocessable()->assertJsonValidationErrors('modulo');
        $this->postJson('/api/faq-itens', $this->dados(['pergunta' => 'ab']))->assertUnprocessable()->assertJsonValidationErrors('pergunta');
        $this->postJson('/api/faq-itens', $this->dados(['resposta' => '']))->assertUnprocessable()->assertJsonValidationErrors('resposta');
        $this->postJson('/api/faq-itens', array_diff_key($this->dados(), ['palavras_chave' => 1]))->assertCreated()->assertJsonPath('palavras_chave', []);
    }

    public function test_limite_de_respostas_extras(): void
    {
        for ($i = 0; $i < 100; $i++) {
            FaqItem::create($this->dados(['pergunta' => "Pergunta número {$i}"]));
        }

        $this->postJson('/api/faq-itens', $this->dados())->assertUnprocessable();
    }

    public function test_nem_o_administrador_com_todas_as_permissoes_mexe_no_faq(): void
    {
        $this->entrarComo($this->criarUsuario(Acesso::todas(), Usuario::ADMIN, 'admin@lume.test'));

        $this->getJson('/api/faq-itens')->assertForbidden();
        $this->postJson('/api/faq-itens', $this->dados())->assertForbidden();
        $this->assertDatabaseCount('faq_itens', 0);
    }

    public function test_so_o_master_recebe_a_permissao_faq_responder(): void
    {
        $this->assertContains(Acesso::SO_MASTER, Acesso::permissoesDe($this->criarMaster('outro@lume.test')));
        $this->assertNotContains(Acesso::SO_MASTER, Acesso::permissoesDe($this->criarUsuario(Acesso::todas(), Usuario::ADMIN, 'a@lume.test')));
        $this->assertNotContains(Acesso::SO_MASTER, Acesso::limpar([Acesso::SO_MASTER, 'clientes.ver'])); // um grupo não consegue guardá-la
    }

    public function test_sem_login_nao_entra(): void
    {
        $this->semLogin()->getJson('/api/faq-itens')->assertUnauthorized();
    }
}
