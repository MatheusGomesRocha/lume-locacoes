<?php

namespace Tests\Feature;

use App\Models\Grupo;
use App\Models\TokenAcesso;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class UsuarioApiTest extends TestCase
{
    use RefreshDatabase;

    private Usuario $master;

    protected function setUp(): void
    {
        parent::setUp(); // já entra como master (teste@lume.test)
        $this->master = Usuario::where('papel', Usuario::MASTER)->firstOrFail();
    }

    private function grupo(array $permissoes = ['clientes.ver']): Grupo
    {
        return Grupo::create(['nome' => 'G'.uniqid(), 'permissoes' => $permissoes]);
    }

    private function dados(array $extra = []): array
    {
        return array_merge(['nome' => 'Novo', 'email' => 'novo@lume.test', 'senha' => 'senha1234', 'papel' => 'usuario', 'grupo_id' => $this->grupo()->id, 'ativo' => true], $extra);
    }

    private function admin(string $email = 'admin@lume.test'): Usuario
    {
        return $this->criarUsuario(['usuarios.ver', 'usuarios.criar', 'usuarios.editar', 'usuarios.excluir'], Usuario::ADMIN, $email);
    }

    public function test_lista_com_o_grupo_e_sem_a_senha(): void
    {
        $this->criarUsuario();

        $r = $this->getJson('/api/usuarios')->assertOk();

        $this->assertCount(2, $r->json());
        $this->assertArrayNotHasKey('senha', $r->json(0));
        $this->assertNotEmpty($r->json('0.grupo.nome'));
    }

    public function test_master_cadastra_usuario_e_admin_e_guarda_o_hash_da_senha(): void
    {
        $r = $this->postJson('/api/usuarios', $this->dados(['email' => 'NOVO@Lume.Test', 'papel' => 'admin']))->assertCreated();

        $r->assertJsonPath('papel', 'admin')->assertJsonPath('email', 'novo@lume.test');
        $this->assertTrue(Hash::check('senha1234', Usuario::find($r->json('id'))->senha));
    }

    public function test_valida_campos_obrigatorios(): void
    {
        $this->postJson('/api/usuarios', [])->assertUnprocessable()->assertJsonValidationErrors(['nome', 'email', 'senha', 'grupo_id']);
        $this->postJson('/api/usuarios', $this->dados(['senha' => 'curta']))->assertUnprocessable()->assertJsonValidationErrors('senha');
        $this->postJson('/api/usuarios', $this->dados(['grupo_id' => 9999]))->assertUnprocessable()->assertJsonValidationErrors('grupo_id');
        $this->postJson('/api/usuarios', $this->dados(['email' => 'não é email']))->assertUnprocessable()->assertJsonValidationErrors('email');
    }

    public function test_email_e_unico_sem_diferenciar_maiusculas(): void
    {
        $this->postJson('/api/usuarios', $this->dados(['email' => 'novo@lume.test']))->assertCreated();
        $this->postJson('/api/usuarios', $this->dados(['email' => 'NOVO@lume.test']))->assertUnprocessable()->assertJsonValidationErrors('email');
    }

    public function test_ninguem_cria_outro_master_nem_usa_o_grupo_master(): void
    {
        $this->postJson('/api/usuarios', $this->dados(['papel' => 'master']))->assertUnprocessable()->assertJsonValidationErrors('papel');
        $this->postJson('/api/usuarios', $this->dados(['grupo_id' => $this->master->grupo_id]))->assertUnprocessable()->assertJsonValidationErrors('grupo_id');
    }

    public function test_admin_cadastra_apenas_usuarios_comuns(): void
    {
        $this->entrarComo($this->admin());

        $this->postJson('/api/usuarios', $this->dados(['papel' => 'admin']))->assertCreated()->assertJsonPath('papel', 'usuario');
    }

    public function test_admin_nao_edita_nem_exclui_master_nem_outro_admin(): void
    {
        $outro = $this->admin('outro@lume.test');
        $this->entrarComo($this->admin());

        $this->putJson("/api/usuarios/{$this->master->id}", $this->dados(['nome' => 'Hack', 'email' => 'teste@lume.test']))->assertForbidden();
        $this->deleteJson("/api/usuarios/{$this->master->id}")->assertUnprocessable();
        $this->putJson("/api/usuarios/{$outro->id}", $this->dados(['email' => 'outro@lume.test']))->assertForbidden();
        $this->deleteJson("/api/usuarios/{$outro->id}")->assertForbidden();
        $this->assertSame('Master', $this->master->fresh()->nome);
    }

    public function test_admin_edita_usuario_comum_mas_nao_o_promove(): void
    {
        $comum = $this->criarUsuario(['clientes.ver'], Usuario::USUARIO, 'comum@lume.test');
        $this->entrarComo($this->admin());

        $this->putJson("/api/usuarios/{$comum->id}", $this->dados(['email' => 'comum@lume.test', 'papel' => 'admin', 'nome' => 'Editado']))
            ->assertOk()->assertJsonPath('nome', 'Editado')->assertJsonPath('papel', 'usuario');
    }

    public function test_so_o_master_promove_a_admin(): void
    {
        $comum = $this->criarUsuario(['clientes.ver'], Usuario::USUARIO, 'comum@lume.test');

        $this->putJson("/api/usuarios/{$comum->id}", $this->dados(['email' => 'comum@lume.test', 'papel' => 'admin']))->assertOk()->assertJsonPath('papel', 'admin');
    }

    public function test_usuario_comum_nao_gerencia_ninguem_mesmo_com_a_permissao_no_grupo(): void
    {
        $this->entrarComo($this->criarUsuario(['usuarios.ver', 'usuarios.criar', 'usuarios.editar', 'usuarios.excluir']));

        $this->getJson('/api/usuarios')->assertForbidden();
        $this->postJson('/api/usuarios', $this->dados())->assertForbidden();
        $this->getJson('/api/grupos')->assertForbidden();
    }

    public function test_admin_sem_a_permissao_do_grupo_tambem_nao(): void
    {
        $this->entrarComo($this->criarUsuario(['usuarios.ver'], Usuario::ADMIN));

        $this->getJson('/api/usuarios')->assertOk();
        $this->postJson('/api/usuarios', $this->dados())->assertForbidden();
    }

    public function test_master_altera_so_nome_email_e_senha(): void
    {
        $r = $this->putJson("/api/usuarios/{$this->master->id}", $this->dados(['nome' => 'Dono', 'email' => 'teste@lume.test', 'papel' => 'usuario', 'ativo' => false, 'grupo_id' => $this->grupo()->id, 'senha' => 'outrasenha1']))
            ->assertOk();

        $r->assertJsonPath('nome', 'Dono')->assertJsonPath('papel', 'master')->assertJsonPath('ativo', true);
        $m = $this->master->fresh();
        $this->assertSame($this->master->grupo_id, $m->grupo_id);
        $this->assertTrue(Hash::check('outrasenha1', $m->senha));
    }

    public function test_ninguem_exclui_a_si_mesmo_nem_o_master(): void
    {
        $this->deleteJson("/api/usuarios/{$this->master->id}")->assertUnprocessable();
        $outro = $this->admin();
        $this->entrarComo($outro);
        $this->deleteJson("/api/usuarios/{$outro->id}")->assertUnprocessable();
    }

    public function test_master_exclui_usuario_e_as_sessoes_dele_somem(): void
    {
        $u = $this->criarUsuario();
        TokenAcesso::emitir($u);

        $this->deleteJson("/api/usuarios/{$u->id}")->assertNoContent();

        $this->assertDatabaseMissing('usuarios', ['id' => $u->id]);
        $this->assertDatabaseCount('tokens_acesso', 1); // só a do master do teste
    }

    public function test_desativar_ou_trocar_a_senha_derruba_as_sessoes_abertas(): void
    {
        $u = $this->criarUsuario(['clientes.ver'], Usuario::USUARIO, 'comum@lume.test');
        $token = TokenAcesso::emitir($u);
        $dados = $this->dados(['email' => 'comum@lume.test', 'grupo_id' => $u->grupo_id, 'senha' => null]);

        $this->putJson("/api/usuarios/{$u->id}", $dados)->assertOk(); // só editar, sem senha nova, não derruba
        $this->assertDatabaseHas('tokens_acesso', ['token_hash' => TokenAcesso::hash($token)]);

        $this->putJson("/api/usuarios/{$u->id}", array_merge($dados, ['senha' => 'outrasenha1']))->assertOk();
        $this->assertDatabaseMissing('tokens_acesso', ['token_hash' => TokenAcesso::hash($token)]);

        $token = TokenAcesso::emitir($u);
        $this->putJson("/api/usuarios/{$u->id}", array_merge($dados, ['ativo' => false]))->assertOk();
        $this->assertDatabaseMissing('tokens_acesso', ['token_hash' => TokenAcesso::hash($token)]);
    }

    public function test_admin_nao_edita_a_si_mesmo_por_esta_rota(): void
    {
        $adm = $this->admin();
        $this->entrarComo($adm);

        $this->putJson("/api/usuarios/{$adm->id}", $this->dados(['email' => 'admin@lume.test', 'papel' => 'admin', 'grupo_id' => $adm->grupo_id]))->assertForbidden();
    }

    public function test_master_desativa_e_rebaixa_outro_admin(): void
    {
        $adm = $this->admin();

        $this->putJson("/api/usuarios/{$adm->id}", $this->dados(['email' => 'admin@lume.test', 'papel' => 'usuario', 'grupo_id' => $adm->grupo_id, 'ativo' => false]))
            ->assertOk()->assertJsonPath('papel', 'usuario')->assertJsonPath('ativo', false);
    }

    public function test_grupo_master_nao_pode_ser_dado_a_outra_pessoa(): void
    {
        $u = $this->criarUsuario();

        $this->putJson("/api/usuarios/{$u->id}", $this->dados(['email' => 'pessoa@lume.test', 'grupo_id' => $this->master->grupo_id]))->assertUnprocessable()->assertJsonValidationErrors('grupo_id');
    }

    public function test_catalogo_de_permissoes_nao_vaza_chaves_desconhecidas_ao_usuario(): void
    {
        $u = $this->criarUsuario(['clientes.ver', 'inventada.x']);

        $this->assertSame(['clientes.ver'], Acesso::permissoesDe($u->load('grupo')));
    }
}
