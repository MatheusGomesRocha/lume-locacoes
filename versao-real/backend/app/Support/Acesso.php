<?php

namespace App\Support;

use App\Models\Usuario;

/**
 * Catálogo de permissões: espelho de frontend/src/lib/permissoes.ts.
 * A chave é "modulo.acao". Se mudar aqui, mude lá (há um teste que compara os dois arquivos).
 */
final class Acesso
{
    public const CRUD = ['ver', 'criar', 'editar', 'excluir'];

    public const MODULOS = [
        'painel' => ['ver'],
        'orcamentos' => ['ver', 'criar', 'editar', 'excluir', 'enviar', 'aprovar', 'finalizar', 'cancelar'],
        'financeiro' => ['ver', 'baixar'],
        'produtos' => self::CRUD,
        'clientes' => self::CRUD,
        'assistente' => ['usar', 'conversas'],
        'usuarios' => self::CRUD,
    ];

    /** @return list<string> */
    public static function todas(): array
    {
        $lista = [];
        foreach (self::MODULOS as $modulo => $acoes) {
            foreach ($acoes as $acao) {
                $lista[] = "$modulo.$acao";
            }
        }

        return $lista;
    }

    /**
     * Descarta chaves desconhecidas e repetidas.
     *
     * @param  array<int, mixed>  $lista
     * @return list<string>
     */
    public static function limpar(array $lista): array
    {
        return array_values(array_unique(array_filter($lista, fn ($p) => is_string($p) && in_array($p, self::todas(), true))));
    }

    /** @return list<string> */
    public static function permissoesDe(Usuario $u): array
    {
        if ($u->papel === Usuario::MASTER) {
            return self::todas();
        }

        return self::limpar($u->grupo?->permissoes ?? []);
    }

    /** Quem pode mexer em quem: o master só em si mesmo; master em todos; admin só em usuários comuns. */
    public static function podeGerenciar(Usuario $ator, Usuario $alvo): bool
    {
        if ($alvo->papel === Usuario::MASTER) {
            return $ator->id === $alvo->id;
        }

        return match ($ator->papel) {
            Usuario::MASTER => true,
            Usuario::ADMIN => $alvo->papel === Usuario::USUARIO,
            default => false,
        };
    }
}
