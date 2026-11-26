<?php

namespace App\Http\Middleware;

use App\Models\Usuario;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class ExigeMaster
{
    public function handle(Request $request, Closure $next): Response
    {
        if ($request->attributes->get('usuario')?->papel !== Usuario::MASTER) {
            return response()->json(['message' => 'Você não tem permissão para esta ação.'], 403);
        }

        return $next($request);
    }
}
