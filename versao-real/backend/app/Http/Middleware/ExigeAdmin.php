<?php

namespace App\Http\Middleware;

use App\Models\Usuario;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/** As permissões "usuarios.*" só valem para administradores e para o master, mesmo que o grupo as inclua. */
class ExigeAdmin
{
    public function handle(Request $request, Closure $next): Response
    {
        if (! in_array($request->attributes->get('usuario')?->papel, [Usuario::MASTER, Usuario::ADMIN], true)) {
            return response()->json(['message' => 'Você não tem permissão para esta ação.'], 403);
        }

        return $next($request);
    }
}
