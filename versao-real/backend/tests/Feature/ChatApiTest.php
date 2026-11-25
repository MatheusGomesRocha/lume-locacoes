<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ChatApiTest extends TestCase
{
    public function test_repassa_a_pergunta_para_a_api_python_e_devolve_a_resposta(): void
    {
        Http::fake(['ia.test/chat' => Http::response(['encontrou' => true, 'resposta' => 'Abra Orçamentos.', 'fonte' => 'orc-criar', 'confianca' => 0.8, 'relacionadas' => []])]);

        $this->postJson('/api/chat', ['pergunta' => 'Como criar um orçamento?'])
            ->assertOk()->assertJsonPath('resposta', 'Abra Orçamentos.')->assertJsonPath('encontrou', true);

        Http::assertSent(fn ($r) => $r->url() === 'http://ia.test/chat' && $r['pergunta'] === 'Como criar um orçamento?');
    }

    public function test_envia_o_token_quando_configurado(): void
    {
        config(['services.ia.token' => 'segredo']);
        Http::fake(['ia.test/*' => Http::response(['resposta' => 'ok'])]);

        $this->postJson('/api/chat', ['pergunta' => 'oi tudo bem'])->assertOk();

        Http::assertSent(fn ($r) => $r->hasHeader('X-API-Token', 'segredo'));
    }

    public function test_nao_envia_header_de_token_quando_nao_configurado(): void
    {
        Http::fake(['ia.test/*' => Http::response(['resposta' => 'ok'])]);

        $this->postJson('/api/chat', ['pergunta' => 'oi tudo bem'])->assertOk();

        Http::assertSent(fn ($r) => ! $r->hasHeader('X-API-Token'));
    }

    public function test_valida_a_pergunta(): void
    {
        Http::fake();

        $this->postJson('/api/chat', [])->assertStatus(422)->assertJsonValidationErrors(['pergunta']);
        $this->postJson('/api/chat', ['pergunta' => 'a'])->assertStatus(422);
        $this->postJson('/api/chat', ['pergunta' => str_repeat('a', 501)])->assertStatus(422);
        Http::assertNothingSent();
    }

    public function test_devolve_503_amigavel_se_a_api_python_cair(): void
    {
        Http::fake(['ia.test/*' => Http::response('erro', 500)]);

        $this->postJson('/api/chat', ['pergunta' => 'Como criar um orçamento?'])
            ->assertStatus(503)->assertJsonPath('encontrou', false)->assertJsonPath('resposta', fn ($t) => str_contains($t, 'indisponível'));
    }

    public function test_devolve_503_se_a_conexao_falhar(): void
    {
        Http::fake(fn () => throw new \Illuminate\Http\Client\ConnectionException('sem rede'));

        $this->postJson('/api/chat', ['pergunta' => 'Como criar um orçamento?'])->assertStatus(503);
    }

    public function test_sugestoes_vem_do_faq_e_sao_no_maximo_seis(): void
    {
        $faq = array_map(fn ($i) => ['id' => "f$i", 'pergunta' => "Pergunta $i?"], range(1, 10));
        Http::fake(['ia.test/faq' => Http::response($faq)]);

        $r = $this->getJson('/api/chat/sugestoes')->assertOk()->json();

        $this->assertCount(6, $r);
        $this->assertStringStartsWith('Pergunta', $r[0]);
    }

    public function test_sugestoes_voltam_vazias_se_a_api_estiver_fora(): void
    {
        Http::fake(['ia.test/*' => Http::response('x', 500)]);

        $this->getJson('/api/chat/sugestoes')->assertOk()->assertExactJson([]);
    }

    public function test_repassa_o_contexto_da_conversa_para_a_api(): void
    {
        config(['services.ia.url' => 'http://ia.test']);
        Http::fake(['ia.test/chat' => Http::response(['encontrou' => true, 'resposta' => 'ok', 'fonte' => null, 'confianca' => 1, 'relacionadas' => []])]);

        $this->postJson('/api/chat', ['pergunta' => 'mas eu quero excluir', 'historico' => ['e pra excluir produtos?', '  '], 'ultimo_id' => 'prod-excluir'])->assertOk();

        Http::assertSent(fn ($r) => $r['pergunta'] === 'mas eu quero excluir'
            && $r['historico'] === ['e pra excluir produtos?']
            && $r['ultimo_id'] === 'prod-excluir');
    }

    public function test_sem_contexto_nao_manda_campos_extras(): void
    {
        config(['services.ia.url' => 'http://ia.test']);
        Http::fake(['ia.test/chat' => Http::response(['encontrou' => true, 'resposta' => 'ok', 'fonte' => null, 'confianca' => 1, 'relacionadas' => []])]);

        $this->postJson('/api/chat', ['pergunta' => 'Como criar um orçamento?', 'historico' => [], 'ultimo_id' => null])->assertOk();

        Http::assertSent(fn ($r) => $r->data() === ['pergunta' => 'Como criar um orçamento?']);
    }

    public function test_valida_o_contexto(): void
    {
        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'historico' => array_fill(0, 7, 'a')])->assertStatus(422)->assertJsonValidationErrors(['historico']);
        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'historico' => [str_repeat('a', 501)]])->assertStatus(422);
        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'ultimo_id' => str_repeat('x', 81)])->assertStatus(422);
    }
}
