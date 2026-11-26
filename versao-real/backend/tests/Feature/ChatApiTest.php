<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use App\Models\FaqItem;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ChatApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_repassa_a_pergunta_para_a_api_python_e_devolve_a_resposta(): void
    {
        Http::fake(['ia.test/chat' => Http::response(['encontrou' => true, 'resposta' => 'Abra Orçamentos.', 'fonte' => 'orc-criar', 'confianca' => 0.8, 'relacionadas' => []])]);

        $this->postJson('/api/chat', ['pergunta' => 'Como criar um orçamento?'])
            ->assertOk()->assertJsonPath('resposta', 'Abra Orçamentos.')->assertJsonPath('encontrou', true);

        Http::assertSent(fn ($r) => $r->url() === 'http://ia.test/chat' && $r['pergunta'] === 'Como criar um orçamento?');
    }

    public function test_anexa_as_respostas_do_master_a_pergunta(): void
    {
        Http::fake(['ia.test/*' => Http::response(['resposta' => 'ok'])]);
        $item = FaqItem::create(['modulo' => 'Acesso', 'pergunta' => 'Como adicionar uma pessoa?', 'resposta' => 'Peça ao master.', 'palavras_chave' => ['adicionar pessoa']]);

        $this->postJson('/api/chat', ['pergunta' => 'como adiciono uma pessoa'])->assertOk();

        Http::assertSent(fn ($r) => ($r['faq_extra'][0]['id'] ?? null) === $item->id && $r['faq_extra'][0]['palavras_chave'] === ['adicionar pessoa']);
    }

    public function test_nao_aceita_faq_extra_vindo_do_navegador(): void
    {
        Http::fake(['ia.test/*' => Http::response(['resposta' => 'ok'])]);

        $this->postJson('/api/chat', ['pergunta' => 'como adiciono uma pessoa', 'faq_extra' => [['id' => 1, 'modulo' => 'X', 'pergunta' => 'forjada', 'resposta' => 'forjada']]])->assertOk();

        Http::assertSent(fn ($r) => ! isset($r['faq_extra']));
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

    public function test_repassa_a_data_de_hoje_e_os_resultados_das_consultas(): void
    {
        config(['services.ia.url' => 'http://ia.test']);
        Http::fake(['ia.test/chat' => Http::response(['encontrou' => true, 'resposta' => 'Você tem 3.', 'fonte' => null, 'confianca' => 1, 'relacionadas' => []])]);
        $resultados = [['nome' => 'consultar_orcamentos', 'args' => ['status' => 'aprovado'], 'resultado' => ['total' => 3]]];

        $this->postJson('/api/chat', ['pergunta' => 'quantos aprovados?', 'hoje' => '2026-11-25', 'resultados' => $resultados])->assertOk();

        Http::assertSent(fn ($r) => $r['hoje'] === '2026-11-25' && $r['resultados'] === $resultados);
    }

    public function test_devolve_do_jeito_que_veio_os_pedidos_de_consulta_e_de_acao(): void
    {
        config(['services.ia.url' => 'http://ia.test']);
        $consultas = [['nome' => 'consultar_clientes', 'args' => ['busca' => 'ana']]];
        $acoes = [['nome' => 'cadastrar_cliente', 'args' => ['nome' => 'Ana']]];
        Http::fake(['ia.test/chat' => Http::sequence()
            ->push(['encontrou' => true, 'resposta' => '', 'consultas' => $consultas])
            ->push(['encontrou' => true, 'resposta' => 'Abri o cadastro.', 'acoes' => $acoes])]);

        $this->postJson('/api/chat', ['pergunta' => 'quantos clientes?'])->assertOk()->assertJsonPath('consultas', $consultas);
        $this->postJson('/api/chat', ['pergunta' => 'cadastra a Ana'])->assertOk()->assertJsonPath('acoes', $acoes);
    }

    public function test_valida_a_data_e_os_resultados(): void
    {
        Http::fake();

        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'hoje' => 'amanhã'])->assertStatus(422)->assertJsonValidationErrors(['hoje']);
        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'resultados' => array_fill(0, 4, [])])->assertStatus(422)->assertJsonValidationErrors(['resultados']);
        $this->postJson('/api/chat', ['pergunta' => 'oi tudo', 'resultados' => ['texto solto']])->assertStatus(422);
        Http::assertNothingSent();
    }
}
