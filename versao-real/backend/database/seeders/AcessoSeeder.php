<?php

namespace Database\Seeders;

use App\Models\Grupo;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

/**
 * Cria o grupo Master e o usuário master. Em produção a senha vem de MASTER_SENHA (e o e-mail de MASTER_EMAIL);
 * sem ela nenhum usuário é criado. Fora de produção usa master@lume.com / lume1234 e cria contas de exemplo.
 * Rodar de novo não troca senha nem duplica ninguém.
 */
class AcessoSeeder extends Seeder
{
    public function run(): void
    {
        $producao = app()->environment('production');
        $email = mb_strtolower(trim((string) env('MASTER_EMAIL', $producao ? '' : 'master@lume.com')));
        $senha = (string) env('MASTER_SENHA', $producao ? '' : 'lume1234');

        $grupoMaster = Grupo::firstOrCreate(
            ['nome' => 'Master'],
            ['descricao' => 'Acesso total. Não pode ser alterado.', 'permissoes' => Acesso::todas(), 'sistema' => true],
        );
        // se o catálogo de permissões crescer, o grupo do master acompanha
        $grupoMaster->update(['permissoes' => Acesso::todas(), 'sistema' => true]);

        if ($email === '' || strlen($senha) < 8) {
            $this->command?->warn('MASTER_EMAIL / MASTER_SENHA ausentes (senha com 8+ caracteres): nenhum usuário master foi criado.');

            return;
        }

        Usuario::firstOrCreate(
            ['email' => $email],
            ['nome' => 'Master', 'senha' => Hash::make($senha), 'papel' => Usuario::MASTER, 'grupo_id' => $grupoMaster->id, 'ativo' => true],
        );

        if ($producao && ! env('SEED_USUARIOS_DEMO')) {
            return;
        }

        $atendimento = Grupo::firstOrCreate(['nome' => 'Atendimento'], [
            'descricao' => 'Monta orçamentos e cuida de clientes.',
            'permissoes' => ['painel.ver', 'orcamentos.ver', 'orcamentos.criar', 'orcamentos.editar', 'orcamentos.enviar', 'clientes.ver', 'clientes.criar', 'clientes.editar', 'produtos.ver', 'assistente.usar'],
        ]);
        $financeiro = Grupo::firstOrCreate(['nome' => 'Financeiro'], [
            'descricao' => 'Acompanha e dá baixa nas cobranças.',
            'permissoes' => ['painel.ver', 'orcamentos.ver', 'financeiro.ver', 'financeiro.baixar', 'clientes.ver', 'assistente.usar'],
        ]);
        $administracao = Grupo::firstOrCreate(['nome' => 'Administração'], ['descricao' => 'Tudo, inclusive cadastrar usuários.', 'permissoes' => Acesso::todas()]);

        foreach ([
            ['Ana Administradora', 'admin@lume.com', Usuario::ADMIN, $administracao],
            ['Bruno do Atendimento', 'atendimento@lume.com', Usuario::USUARIO, $atendimento],
            ['Carla do Financeiro', 'financeiro@lume.com', Usuario::USUARIO, $financeiro],
        ] as [$nome, $mail, $papel, $grupo]) {
            Usuario::firstOrCreate(['email' => $mail], ['nome' => $nome, 'senha' => Hash::make('lume1234'), 'papel' => $papel, 'grupo_id' => $grupo->id, 'ativo' => true]);
        }
    }
}
