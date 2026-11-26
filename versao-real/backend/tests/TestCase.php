<?php

namespace Tests;

use App\Models\Grupo;
use App\Models\TokenAcesso;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Support\Facades\Hash;

abstract class TestCase extends BaseTestCase
{
    /** Testes de regra de negócio rodam logados como master; os de acesso desligam isto e entram como quiserem. */
    protected bool $logarComoMaster = true;

    protected function setUp(): void
    {
        parent::setUp();

        if ($this->logarComoMaster) {
            $this->entrarComo($this->criarMaster());
        }
    }

    protected function criarMaster(string $email = 'teste@lume.test'): Usuario
    {
        $grupo = Grupo::firstOrCreate(['nome' => 'Master'], ['permissoes' => Acesso::todas(), 'sistema' => true]);

        return Usuario::create(['nome' => 'Master', 'email' => $email, 'senha' => Hash::make('senha1234'), 'papel' => Usuario::MASTER, 'grupo_id' => $grupo->id, 'ativo' => true]);
    }

    /** Cria um grupo e um usuário nele (papel padrão: usuário comum). */
    protected function criarUsuario(array $permissoes = [], string $papel = Usuario::USUARIO, string $email = 'pessoa@lume.test', bool $ativo = true): Usuario
    {
        $grupo = Grupo::create(['nome' => 'Grupo '.uniqid(), 'permissoes' => $permissoes, 'sistema' => false]);

        return Usuario::create(['nome' => 'Pessoa', 'email' => $email, 'senha' => Hash::make('senha1234'), 'papel' => $papel, 'grupo_id' => $grupo->id, 'ativo' => $ativo]);
    }

    /** Passa a enviar o token deste usuário em todas as chamadas seguintes do teste. */
    protected function entrarComo(Usuario $usuario): static
    {
        $this->flushHeaders();

        return $this->withToken(TokenAcesso::emitir($usuario));
    }

    protected function semLogin(): static
    {
        return $this->flushHeaders();
    }
}
