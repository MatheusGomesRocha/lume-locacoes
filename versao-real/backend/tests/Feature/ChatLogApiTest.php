<?php

namespace Tests\Feature;

use App\Models\ChatLog;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ChatLogApiTest extends TestCase
{
    use RefreshDatabase;

    private function dados(array $extra = []): array
    {
        return array_merge([
            'pergunta' => 'Como crio um orçamento?',
            'resposta' => 'Vá em Orçamentos.',
            'tipo' => 'ajuda',
            'fonte_id' => 'faq-1',
            'ferramenta' => null,
            'gerada_por_llm' => true,
            'em_cache' => false,
            'usou_contexto' => false,
            'latencia_ms' => 850,
            'voltas' => 1,
        ], $extra);
    }

    public function test_registra_uma_pergunta(): void
    {
        $this->postJson('/api/chat-logs', $this->dados())
            ->assertCreated()
            ->assertJsonPath('tipo', 'ajuda')
            ->assertJsonPath('gerada_por_llm', true)
            ->assertJsonPath('feedback', null)
            ->assertJsonStructure(['id', 'criado_em']);

        $this->assertDatabaseCount('chat_logs', 1);
    }

    public function test_guarda_tokens_custo_e_versao_da_pergunta(): void
    {
        $this->postJson('/api/chat-logs', $this->dados(['tokens_entrada' => 1200, 'tokens_saida' => 80, 'custo_usd' => 0.000152, 'versao' => 'a1b2c3d']))
            ->assertCreated()->assertJsonPath('tokens_entrada', 1200)->assertJsonPath('tokens_saida', 80)->assertJsonPath('versao', 'a1b2c3d');
        $this->postJson('/api/chat-logs', $this->dados())->assertCreated()->assertJsonPath('tokens_entrada', 0)->assertJsonPath('versao', null); // sem consumo: zero
        $this->postJson('/api/chat-logs', $this->dados(['tokens_entrada' => -1]))->assertUnprocessable()->assertJsonValidationErrors('tokens_entrada');
    }

    public function test_valida_tipo_e_tamanho(): void
    {
        $this->postJson('/api/chat-logs', $this->dados(['tipo' => 'outro']))->assertUnprocessable()->assertJsonValidationErrors('tipo');
        $this->postJson('/api/chat-logs', $this->dados(['pergunta' => str_repeat('a', 501)]))->assertUnprocessable()->assertJsonValidationErrors('pergunta');
        $this->postJson('/api/chat-logs', [])->assertUnprocessable();
    }

    public function test_lista_do_mais_novo_ao_mais_antigo_com_filtros(): void
    {
        ChatLog::create($this->dados(['pergunta' => 'primeira']));
        ChatLog::create($this->dados(['pergunta' => 'segunda', 'tipo' => 'nao_encontrou', 'feedback' => 'negativo']));

        $this->getJson('/api/chat-logs')->assertOk()->assertJsonPath('0.pergunta', 'segunda')->assertJsonCount(2);
        $this->getJson('/api/chat-logs?tipo=nao_encontrou')->assertJsonCount(1);
        $this->getJson('/api/chat-logs?feedback=negativo')->assertJsonCount(1)->assertJsonPath('0.pergunta', 'segunda');
    }

    public function test_aceita_o_desfecho_ignorado(): void
    {
        $log = ChatLog::create($this->dados(['tipo' => 'nao_encontrou']));

        $this->patchJson("/api/chat-logs/{$log->id}", ['desfecho' => 'ignorado'])->assertOk()->assertJsonPath('desfecho', 'ignorado');
        $this->patchJson("/api/chat-logs/{$log->id}", ['desfecho' => 'qualquer'])->assertUnprocessable();
    }

    public function test_guarda_feedback_e_desfecho(): void
    {
        $log = ChatLog::create($this->dados());

        $this->patchJson("/api/chat-logs/{$log->id}", ['feedback' => 'positivo', 'desfecho' => 'concluido'])
            ->assertOk()->assertJsonPath('feedback', 'positivo')->assertJsonPath('desfecho', 'concluido');

        $this->patchJson("/api/chat-logs/{$log->id}", ['feedback' => 'ótimo'])->assertUnprocessable();
        $this->patchJson('/api/chat-logs/999', ['feedback' => 'positivo'])->assertNotFound();
    }

    public function test_apaga_todos_os_registros(): void
    {
        ChatLog::create($this->dados());
        ChatLog::create($this->dados());

        $this->deleteJson('/api/chat-logs')->assertNoContent();
        $this->assertDatabaseCount('chat_logs', 0);
    }
}
