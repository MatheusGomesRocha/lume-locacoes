<?php

namespace Tests\Feature;

use App\Models\ChatLog;
use App\Models\EvolucaoProposta;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/** Os 3 Agents propõem consultas novas; só o master analisa e decide, e nada fica ativo sem o "aprovar" dele. */
class EvolucaoApiTest extends TestCase
{
    use RefreshDatabase;

    private function spec(): array
    {
        return ['nome' => 'contar_clientes_por_cidade', 'entidade' => 'clientes', 'operacao' => 'contar', 'permissao' => 'clientes.ver',
            'parametros' => ['cidade' => ['tipo' => 'texto', 'obrigatorio' => true]], 'filtros' => [['campo' => 'cidade', 'op' => 'igual', 'parametro' => 'cidade']],
            'exemplos' => ['quantos clientes em fortaleza', 'clientes de sobral', 'total de clientes por cidade']];
    }

    private function relatorio(array $extra = []): array
    {
        return array_merge(['id' => 'EV-0001', 'titulo' => 'Clientes por cidade', 'decisao_do_analista' => 'criar_consulta', 'perguntas' => ['quantos clientes tenho em Fortaleza?'], 'vezes' => 2,
            'status' => 'pendente', 'veredito' => 'aprovar_recomendado', 'texto' => '# EV-0001', 'proposta' => ['entidade' => 'clientes'], 'pacote' => ['spec' => $this->spec()], 'avaliacao' => null], $extra);
    }

    private function pergunta(string $texto, ?string $desfecho = null): void
    {
        ChatLog::create(['pergunta' => $texto, 'resposta' => 'não sei', 'tipo' => 'nao_encontrou', 'gerada_por_llm' => false, 'em_cache' => false, 'usou_contexto' => false, 'latencia_ms' => 5, 'voltas' => 1, 'desfecho' => $desfecho]);
    }

    private function fakeIa(array $propor = null, array $checar = ['bloqueio' => false, 'achados' => []]): void
    {
        Http::fake([
            'ia.test/evolucao/propor' => Http::response($propor ?? ['relatorios' => [$this->relatorio()]]),
            'ia.test/evolucao/checar' => Http::response($checar),
        ]);
    }

    private function pendente(array $extra = []): EvolucaoProposta
    {
        $rel = $this->relatorio($extra);

        return EvolucaoProposta::create(['codigo' => $rel['id'], 'titulo' => $rel['titulo'], 'veredito' => $rel['veredito'], 'relatorio' => $rel]);
    }

    public function test_sem_perguntas_sem_resposta_nem_chama_a_api(): void
    {
        Http::fake();

        $this->postJson('/api/evolucao/analisar')->assertOk()->assertJsonPath('semPerguntas', true)->assertJsonPath('novos', []);

        Http::assertNothingSent();
    }

    public function test_analisar_guarda_a_proposta_pendente_e_nada_fica_ativo(): void
    {
        $this->fakeIa();
        $this->pergunta('quantos clientes tenho em Fortaleza?');
        $this->pergunta('Quantos clientes tenho em Fortaleza');
        $this->pergunta('pergunta ignorada pelo master', 'ignorado');

        $this->postJson('/api/evolucao/analisar')->assertOk()->assertJsonCount(1, 'novos')->assertJsonPath('novos.0.status', 'pendente')->assertJsonPath('novos.0.ativa', false);

        Http::assertSent(fn ($r) => str_ends_with($r->url(), '/evolucao/propor') && $r['perguntas'] === [['pergunta' => 'quantos clientes tenho em Fortaleza?', 'tipo' => 'dados', 'vezes' => 2]] && $r['proximo_numero'] === 1);
        $this->getJson('/api/evolucao/catalogo')->assertOk()->assertExactJson([]);
        $this->getJson('/api/evolucao')->assertOk()->assertJsonPath('0.id', 'EV-0001');
    }

    public function test_nao_analisa_de_novo_a_pergunta_que_ja_tem_proposta(): void
    {
        $this->pendente();
        Http::fake();
        $this->pergunta('quantos clientes tenho em Fortaleza?');

        $this->postJson('/api/evolucao/analisar')->assertOk()->assertJsonPath('semPerguntas', true);
    }

    public function test_api_de_ia_fora_do_ar_da_erro_claro_e_nao_guarda_nada(): void
    {
        Http::fake(['ia.test/*' => Http::response(['detail' => 'sem modelo'], 503)]);
        $this->pergunta('quantos clientes tenho em Fortaleza?');

        $this->postJson('/api/evolucao/analisar')->assertStatus(503)->assertJsonPath('message', 'sem modelo');
        $this->assertDatabaseCount('evolucao_propostas', 0);
    }

    public function test_aprovar_refaz_as_checagens_ativa_e_registra_quem_decidiu(): void
    {
        $this->fakeIa();
        $this->pendente();

        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertOk()->assertJsonPath('status', 'aprovada')->assertJsonPath('ativa', true)->assertJsonPath('decisao.por', 'Master');

        Http::assertSent(fn ($r) => str_ends_with($r->url(), '/evolucao/checar') && $r['spec']['nome'] === 'contar_clientes_por_cidade');
        $this->getJson('/api/evolucao/catalogo')->assertOk()->assertJsonPath('0.nome', 'contar_clientes_por_cidade');
        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => false])->assertUnprocessable(); // já decidida
    }

    public function test_bloqueio_nas_checagens_refeitas_impede_a_aprovacao(): void
    {
        $this->fakeIa(null, ['bloqueio' => true, 'achados' => [['gravidade' => 'bloqueio', 'mensagem' => 'campo secreto']]]);
        $this->pendente();

        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertUnprocessable()->assertJsonPath('message', fn ($m) => str_contains($m, 'campo secreto'));
        $this->getJson('/api/evolucao/catalogo')->assertExactJson([]);
    }

    public function test_sem_resposta_das_checagens_nao_aprova(): void
    {
        Http::fake(['ia.test/*' => Http::response([], 500)]);
        $this->pendente();

        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertStatus(502);
        $this->assertSame('pendente', EvolucaoProposta::first()->status);
    }

    public function test_tester_recomendando_reprovar_so_deixa_reprovar(): void
    {
        $this->fakeIa();
        $this->pendente(['veredito' => 'reprovar_recomendado']);

        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertUnprocessable();
        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => false])->assertOk()->assertJsonPath('status', 'reprovada');
        $this->getJson('/api/evolucao/catalogo')->assertExactJson([]);
    }

    public function test_desativar_tira_a_consulta_do_catalogo(): void
    {
        $this->fakeIa();
        $this->pendente();
        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertOk();

        $this->postJson('/api/evolucao/EV-0001/desativar')->assertOk()->assertJsonPath('ativa', false);
        $this->getJson('/api/evolucao/catalogo')->assertExactJson([]);
        $this->postJson('/api/evolucao/EV-0001/desativar')->assertNotFound();
    }

    public function test_o_chat_leva_so_as_consultas_aprovadas_e_ativas_e_ignora_as_do_navegador(): void
    {
        $this->fakeIa();
        Http::fake(['ia.test/chat' => Http::response(['resposta' => 'ok'])]);
        $this->pendente();

        $this->postJson('/api/chat', ['pergunta' => 'quantos clientes em fortaleza', 'catalogo' => [$this->spec()]])->assertOk();
        Http::assertSent(fn ($r) => str_ends_with($r->url(), '/chat') && ! isset($r['catalogo'])); // pendente e vinda do navegador: nada vai

        EvolucaoProposta::first()->update(['status' => 'aprovada', 'ativa' => true]);
        $this->postJson('/api/chat', ['pergunta' => 'quantos clientes em fortaleza'])->assertOk();
        Http::assertSent(fn ($r) => str_ends_with($r->url(), '/chat') && ($r['catalogo'][0]['nome'] ?? null) === 'contar_clientes_por_cidade');
    }

    public function test_nem_o_administrador_com_todas_as_permissoes_analisa_ou_decide(): void
    {
        $this->pendente();
        $this->entrarComo($this->criarUsuario(Acesso::todas(), Usuario::ADMIN, 'admin@lume.test'));

        $this->getJson('/api/evolucao')->assertForbidden();
        $this->postJson('/api/evolucao/analisar')->assertForbidden();
        $this->postJson('/api/evolucao/EV-0001/decidir', ['aprovar' => true])->assertForbidden();
        $this->postJson('/api/evolucao/EV-0001/desativar')->assertForbidden();
        $this->assertSame('pendente', EvolucaoProposta::first()->status);
    }

    public function test_usuario_comum_le_o_catalogo_mas_sem_login_nao_entra(): void
    {
        $this->entrarComo($this->criarUsuario(['assistente.usar'], Usuario::USUARIO, 'comum@lume.test'));
        $this->getJson('/api/evolucao/catalogo')->assertOk();
        $this->getJson('/api/evolucao')->assertForbidden();

        $this->semLogin()->getJson('/api/evolucao/catalogo')->assertUnauthorized();
    }
}
