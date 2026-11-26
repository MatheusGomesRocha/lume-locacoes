<?php

namespace App\Http\Controllers;

use App\Exceptions\RegraDeNegocioException;
use App\Models\TokenAcesso;
use App\Models\Usuario;
use App\Support\Acesso;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\Rule;

class AuthController extends Controller
{
    /** Hash de uma senha qualquer: gasta o mesmo tempo quando o e-mail não existe (não revela quais e-mails existem). */
    private static function hashFalso(): string
    {
        static $hash = null;

        return $hash ??= Hash::make(bin2hex(random_bytes(16)));
    }

    public static function sessao(Usuario $u): array
    {
        $u->loadMissing('grupo');

        return ['usuario' => $u->paraApi(), 'permissoes' => Acesso::permissoesDe($u)];
    }

    public function login(Request $request): JsonResponse
    {
        $dados = $request->validate(['email' => 'required|string|max:150', 'senha' => 'required|string|max:200']);
        $usuario = Usuario::with('grupo')->where('email', mb_strtolower(trim($dados['email'])))->first();

        $confere = Hash::check($dados['senha'], $usuario?->senha ?? self::hashFalso());
        if (! $usuario || ! $confere) {
            throw new RegraDeNegocioException('E-mail ou senha incorretos.', [], 401);
        }
        if (! $usuario->ativo) {
            throw new RegraDeNegocioException('Este usuário está desativado. Fale com um administrador.', [], 403);
        }

        return response()->json(self::sessao($usuario) + ['token' => TokenAcesso::emitir($usuario)]);
    }

    public function logout(Request $request)
    {
        $request->attributes->get('token_acesso')->delete();

        return response()->noContent();
    }

    public function eu(Request $request): array
    {
        return self::sessao($request->attributes->get('usuario'));
    }

    /** Cada pessoa altera os próprios dados. Papel e grupo não mudam por aqui. */
    public function atualizarEu(Request $request): array
    {
        /** @var Usuario $eu */
        $eu = $request->attributes->get('usuario');
        $request->merge(['email' => mb_strtolower(trim((string) $request->input('email')))]);
        $dados = $request->validate([
            'nome' => 'required|string|max:150',
            'email' => ['required', 'email', 'max:150', Rule::unique('usuarios', 'email')->ignore($eu->id)],
            'nova_senha' => 'nullable|string|min:8|max:200',
            'senha_atual' => 'nullable|string',
        ]);

        if (! empty($dados['nova_senha'])) {
            if (! Hash::check((string) ($dados['senha_atual'] ?? ''), $eu->senha)) {
                throw new RegraDeNegocioException('A senha atual não confere.', [], 422);
            }
            $eu->senha = Hash::make($dados['nova_senha']);
            // as outras sessões deste usuário deixam de valer
            $eu->tokens()->where('id', '!=', $request->attributes->get('token_acesso')->id)->delete();
        }
        $eu->fill(['nome' => trim($dados['nome']), 'email' => $dados['email']])->save();

        return self::sessao($eu->fresh('grupo'));
    }
}
