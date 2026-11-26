<?php

namespace App\Http\Controllers;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Foundation\Auth\Access\AuthorizesRequests;
use Illuminate\Http\Request;
use Illuminate\Foundation\Bus\DispatchesJobs;
use Illuminate\Foundation\Validation\ValidatesRequests;
use Illuminate\Routing\Controller as BaseController;

class Controller extends BaseController
{
    use AuthorizesRequests, DispatchesJobs, ValidatesRequests;

    /** Máximo de itens por página que o servidor aceita. */
    public const MAXIMO_POR_PAGINA = 100;

    /**
     * Lista com paginação quando o pedido traz `por_pagina` (e `pagina`); sem `por_pagina` devolve tudo, como antes.
     * Quem precisa da lista inteira (campos de escolha, o assistente contando registros) continua pedindo sem paginar.
     * `$mapa` transforma cada item para o formato da API.
     */
    protected function listaPaginada(Request $request, Builder $consulta, ?callable $mapa = null)
    {
        $por = (int) $request->query('por_pagina', 0);
        if ($por < 1) {
            $todos = $consulta->get();

            return $mapa ? $todos->map($mapa)->values() : $todos;
        }

        $p = $consulta->paginate(min($por, self::MAXIMO_POR_PAGINA), ['*'], 'pagina', max(1, (int) $request->query('pagina', 1)));
        $itens = collect($p->items());

        return [
            'dados' => ($mapa ? $itens->map($mapa) : $itens)->values(),
            'total' => $p->total(),
            'pagina' => $p->currentPage(),
            'por_pagina' => $p->perPage(),
            'ultima_pagina' => $p->lastPage(),
        ];
    }
}
