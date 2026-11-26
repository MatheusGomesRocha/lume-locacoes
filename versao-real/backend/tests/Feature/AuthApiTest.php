<?php

namespace Tests\Feature;

use App\Models\TokenAcesso;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AuthApiTest extends TestCase
{
    use RefreshDatabase;

    protected bool $logarComoMaster = false;

    private function login(string $email = 'pessoa@lume.test', string $senha = 'senha1234')
    {
        return $this->postJson('/api/login', ['email' => $email, 'senha' => $senha]);
    }

    public function test_login_devolve_token_usuario_e_permissoes_sem_a_senha(): void
    {
        $this->criarUsuario(['clientes.ver', 'clientes.ver', 'foo.bar']);

        $r = $this->login()->assertOk()->assertJsonStructure(['token', 'usuario' => ['id', 'nome', 'email', 'papel', 'grupo_id', 'grupo' => ['id', 'nome'], 'ativo'], 'permissoes']);

        $this->assertSame(['clientes.ver'], $r->json('permissoes')); // chaves repetidas e desconhecidas são ignoradas
        $this->assertArrayNotHasKey('senha', $r->json('usuario'));
    }

    public function test_so_o_hash_do_token_fica_no_banco(): void
    {
        $this->criarUsuario();
        $token = $this->login()->json('token');

        $this->assertDatabaseMissing('tokens_acesso', ['token_hash' => $token]);
        $this->assertDatabaseHas('tokens_acesso', ['token_hash' => TokenAcesso::hash($token)]);
    }

    public function test_email_nao_diferencia_maiusculas(): void
    {
        $this->criarUsuario();

        $this->login('PESSOA@Lume.Test')->assertOk();
    }

    public function test_senha_errada_e_email_inexistente_dao_a_mesma_resposta(): void
    {
        $this->criarUsuario();

        $a = $this->login('pessoa@lume.test', 'errada1234')->assertUnauthorized();
        $b = $this->login('ninguem@lume.test')->assertUnauthorized();

        $this->assertSame($a->json('message'), $b->json('message'));
    }

    public function test_usuario_desativado_nao_entra(): void
    {
        $this->criarUsuario([], 'usuario', 'pessoa@lume.test', false);

        $this->login()->assertForbidden()->assertJsonPath('message', 'Este usuário está desativado. Fale com um administrador.');
    }

    public function test_tentativas_demais_de_login_sao_barradas(): void
    {
        $this->criarUsuario();

        for ($i = 0; $i < 10; $i++) {
            $this->login('pessoa@lume.test', 'errada1234')->assertUnauthorized();
        }
        $this->login()->assertStatus(429);
    }

    public function test_health_e_login_sao_publicos_e_o_resto_exige_token(): void
    {
        $this->getJson('/api/health')->assertOk();

        foreach ([
            ['getJson', '/api/dashboard'], ['getJson', '/api/clientes'], ['getJson', '/api/produtos'], ['getJson', '/api/orcamentos'],
            ['getJson', '/api/pagamentos'], ['getJson', '/api/usuarios'], ['getJson', '/api/grupos'], ['getJson', '/api/chat-logs'],
            ['getJson', '/api/chat/sugestoes'], ['postJson', '/api/chat'], ['postJson', '/api/clientes'], ['getJson', '/api/eu'],
        ] as [$metodo, $uri]) {
            $this->$metodo($uri)->assertUnauthorized();
        }
    }

    public function test_token_invalido_ou_vencido_nao_vale(): void
    {
        $this->criarUsuario(['clientes.ver']);
        $this->withToken('qualquer-coisa')->getJson('/api/clientes')->assertUnauthorized();

        $token = $this->login()->json('token');
        $this->flushHeaders();
        TokenAcesso::query()->update(['expira_em' => now()->subMinute()]);
        $this->withToken($token)->getJson('/api/clientes')->assertUnauthorized();
    }

    public function test_usuario_desativado_perde_o_acesso_na_proxima_chamada(): void
    {
        $u = $this->criarUsuario(['clientes.ver']);
        $token = $this->login()->json('token');
        $this->withToken($token)->getJson('/api/clientes')->assertOk();

        $u->update(['ativo' => false]);

        $this->withToken($token)->getJson('/api/clientes')->assertUnauthorized();
    }

    public function test_logout_revoga_o_token(): void
    {
        $this->criarUsuario();
        $token = $this->login()->json('token');

        $this->withToken($token)->getJson('/api/eu')->assertOk();
        $this->withToken($token)->postJson('/api/logout')->assertNoContent();
        $this->withToken($token)->getJson('/api/eu')->assertUnauthorized();
    }

    public function test_eu_devolve_as_permissoes_atuais_do_grupo(): void
    {
        $u = $this->criarUsuario(['clientes.ver']);
        $token = $this->login()->json('token');

        $u->grupo->update(['permissoes' => ['clientes.ver', 'produtos.ver']]);

        $this->withToken($token)->getJson('/api/eu')->assertOk()->assertJsonPath('permissoes', ['clientes.ver', 'produtos.ver']);
    }

    public function test_master_tem_todas_as_permissoes(): void
    {
        $this->criarMaster('m@lume.test');

        $this->login('m@lume.test')->assertOk()->assertJsonPath('permissoes', [...Acesso::todas(), Acesso::SO_MASTER]);
    }

    public function test_altera_os_proprios_dados_e_troca_a_senha_com_a_senha_atual(): void
    {
        $this->criarUsuario();
        $token = $this->login()->json('token');
        $outra = $this->login()->json('token'); // segunda sessão

        $this->withToken($token)->putJson('/api/eu', ['nome' => 'Novo Nome', 'email' => 'novo@lume.test'])->assertOk()->assertJsonPath('usuario.nome', 'Novo Nome');
        $this->withToken($token)->putJson('/api/eu', ['nome' => 'X', 'email' => 'novo@lume.test', 'nova_senha' => 'outrasenha1', 'senha_atual' => 'errada'])->assertUnprocessable();
        $this->withToken($token)->putJson('/api/eu', ['nome' => 'X', 'email' => 'novo@lume.test', 'nova_senha' => 'curta', 'senha_atual' => 'senha1234'])->assertUnprocessable();
        $this->withToken($token)->putJson('/api/eu', ['nome' => 'X', 'email' => 'novo@lume.test', 'nova_senha' => 'outrasenha1', 'senha_atual' => 'senha1234'])->assertOk();

        $this->withToken($token)->getJson('/api/eu')->assertOk();            // a sessão atual continua
        $this->withToken($outra)->getJson('/api/eu')->assertUnauthorized();  // as outras caem
        $this->login('novo@lume.test', 'outrasenha1')->assertOk();
    }

    public function test_nao_troca_papel_nem_grupo_por_esta_rota_nem_usa_email_de_outro(): void
    {
        $this->criarUsuario([], 'usuario', 'pessoa@lume.test');
        $this->criarUsuario([], 'usuario', 'outra@lume.test');
        $token = $this->login()->json('token');

        $this->withToken($token)->putJson('/api/eu', ['nome' => 'X', 'email' => 'outra@lume.test'])->assertUnprocessable();
        $this->withToken($token)->putJson('/api/eu', ['nome' => 'X', 'email' => 'pessoa@lume.test', 'papel' => 'master', 'grupo_id' => 1])->assertOk()->assertJsonPath('usuario.papel', 'usuario');
    }

    public function test_o_catalogo_de_permissoes_tem_as_25_chaves_esperadas(): void
    {
        // espelho de frontend/src/lib/permissoes.ts (lá há o mesmo teste): se mudar um, mude o outro
        $this->assertSame([
            'painel.ver',
            'orcamentos.ver', 'orcamentos.criar', 'orcamentos.editar', 'orcamentos.excluir', 'orcamentos.enviar', 'orcamentos.aprovar', 'orcamentos.finalizar', 'orcamentos.cancelar',
            'financeiro.ver', 'financeiro.baixar',
            'produtos.ver', 'produtos.criar', 'produtos.editar', 'produtos.excluir',
            'clientes.ver', 'clientes.criar', 'clientes.editar', 'clientes.excluir',
            'assistente.usar', 'assistente.conversas',
            'usuarios.ver', 'usuarios.criar', 'usuarios.editar', 'usuarios.excluir',
        ], Acesso::todas());
    }
}
