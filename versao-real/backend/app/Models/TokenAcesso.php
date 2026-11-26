<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TokenAcesso extends Model
{
    protected $table = 'tokens_acesso';

    protected $fillable = ['usuario_id', 'token_hash', 'expira_em', 'usado_em'];

    protected $casts = ['expira_em' => 'datetime', 'usado_em' => 'datetime'];

    /** Dias de validade de um login. */
    public const VALIDADE_DIAS = 7;

    public function usuario(): BelongsTo
    {
        return $this->belongsTo(Usuario::class);
    }

    public static function hash(string $token): string
    {
        return hash('sha256', $token);
    }

    /** Cria um token novo e devolve o texto puro (só existe agora; o banco guarda o hash). */
    public static function emitir(Usuario $usuario): string
    {
        $token = bin2hex(random_bytes(32));
        static::create([
            'usuario_id' => $usuario->id,
            'token_hash' => static::hash($token),
            'expira_em' => now()->addDays(self::VALIDADE_DIAS),
        ]);

        return $token;
    }
}
