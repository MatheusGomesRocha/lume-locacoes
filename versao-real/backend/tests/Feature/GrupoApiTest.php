<?php

namespace Tests\Feature;

use App\Models\Grupo;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class GrupoApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_master_cria_grupo_com_permissoes_limpas(): void
    {
        $r = $this->postJson('/api/grupos', ['nome' => 'Atendimento', 'descricao' => 'Balcão', 'permissoes' => ['clientes.ver', 'clientes.ver', 'foo.bar']])->assertCreated();

        $r->assertJsonPath('permissoes', ['clientes.ver'])->assertJsonPath('sistema', false)->assertJsonPath('usuarios_count', 0);
    }

    public function test_valida_nome_obrigatorio_e_unico_e_lista_de_permissoes(): void
    {
        $this->postJson('/api/grupos', ['nome' => '', 'permissoes' => []])->assertUnprocessable()->assertJsonValidationErrors('nome');
        $this->postJson('/api/grupos', ['nome' => 'X'])->assertUnprocessable()->assertJsonValidationErrors('permissoes');
        $this->postJson('/api/grupos', ['nome' => 'Dup', 'permissoes' => []])->assertCreated();
        $this->postJson('/api/grupos', ['nome' => 'Dup', 'permissoes' => []])->assertUnprocessable()->assertJsonValidationErrors('nome');
    }

    public function test_lista_com_contagem_de_usuarios_e_o_grupo_master_com_tudo(): void
    {
        $this->criarUsuario(['clientes.ver']);

        $lista = collect($this->getJson('/api/grupos')->assertOk()->json());
        $master = $lista->firstWhere('sistema', true);

        $this->assertSame(Acesso::todas(), $master['permissoes']);
        $this->assertSame(1, $master['usuarios_count']);
        $this->assertSame(1, $lista->firstWhere('sistema', false)['usuarios_count']);
    }

    public function test_atualiza_e_o_novo_acesso_vale_na_hora(): void
    {
        $u = $this->criarUsuario(['clientes.ver']);
        $this->entrarComo($u);
        $this->getJson('/api/produtos')->assertForbidden();

        $this->entrarComo(Usuario::where('papel', Usuario::MASTER)->first());
        $this->putJson("/api/grupos/{$u->grupo_id}", ['nome' => 'Renomeado', 'descricao' => null, 'permissoes' => ['clientes.ver', 'produtos.ver']])
            ->assertOk()->assertJsonPath('nome', 'Renomeado');

        $this->entrarComo($u);
        $this->getJson('/api/produtos')->assertOk();
    }

    public function test_o_grupo_master_nao_muda_nem_sai(): void
    {
        $id = Grupo::where('sistema', true)->value('id');

        $this->putJson("/api/grupos/{$id}", ['nome' => 'Outro', 'permissoes' => []])->assertForbidden();
        $this->deleteJson("/api/grupos/{$id}")->assertForbidden();
        $this->assertSame(Acesso::todas(), Grupo::find($id)->permissoes);
    }

    public function test_grupo_com_usuarios_nao_e_excluido(): void
    {
        $u = $this->criarUsuario();

        $this->deleteJson("/api/grupos/{$u->grupo_id}")->assertStatus(409);
        $this->assertDatabaseHas('grupos', ['id' => $u->grupo_id]);

        $livre = Grupo::create(['nome' => 'Livre', 'permissoes' => []]);
        $this->deleteJson("/api/grupos/{$livre->id}")->assertNoContent();
    }

    public function test_admin_ve_os_grupos_mas_nao_cria_edita_nem_exclui(): void
    {
        $g = Grupo::create(['nome' => 'Livre', 'permissoes' => []]);
        $this->entrarComo($this->criarUsuario(['usuarios.ver'], Usuario::ADMIN));

        $this->getJson('/api/grupos')->assertOk();
        $this->postJson('/api/grupos', ['nome' => 'Novo', 'permissoes' => []])->assertForbidden();
        $this->putJson("/api/grupos/{$g->id}", ['nome' => 'Mudou', 'permissoes' => []])->assertForbidden();
        $this->deleteJson("/api/grupos/{$g->id}")->assertForbidden();
    }
}
