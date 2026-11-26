<?php

namespace App\Http\Middleware;

use App\Support\Acesso;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Uso: ->middleware('pode:clientes.ver,orcamentos.criar'). Basta ter UMA das permissões listadas.
 * A permissão vem do grupo do usuário a cada requisição, então mudar o grupo vale na hora.
 */
class ExigePermissao
{
    public function handle(Request $request, Closure $next, string ...$permissoes): Response
    {
        $tem = Acesso::permissoesDe($request->attributes->get('usuario'));

        if (! array_intersect($permissoes, $tem)) {
            return response()->json(['message' => 'Você não tem permissão para esta ação.'], 403);
        }

        return $next($request);
    }
}
