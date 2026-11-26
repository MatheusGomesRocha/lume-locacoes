<?php

namespace App\Http\Middleware;

use App\Models\TokenAcesso;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/** Exige "Authorization: Bearer <token>" de um usuário ativo e deixa o usuário em $request->attributes['usuario']. */
class Autenticar
{
    public function handle(Request $request, Closure $next): Response
    {
        $token = $request->bearerToken();
        $registro = $token ? TokenAcesso::with('usuario.grupo')->where('token_hash', TokenAcesso::hash($token))->first() : null;

        if (! $registro || $registro->expira_em->isPast() || ! $registro->usuario?->ativo) {
            return response()->json(['message' => 'Sua sessão expirou. Entre novamente.'], 401);
        }

        $request->attributes->set('usuario', $registro->usuario);
        $request->attributes->set('token_acesso', $registro);

        return $next($request);
    }
}
