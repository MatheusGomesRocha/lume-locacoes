<?php

namespace App\Support;

/**
 * O servidor da API de IA recusa corpos com frases de ataque (ex.: "…; DROP TABLE"), que os testes do Tester usam de propósito.
 * Para o Agent de Aprovação basta a descrição do caso: a frase em si não viaja e é trocada por um aviso.
 */
class SemTextoDeAtaque
{
    public const AVISO = '[texto de injeção omitido no envio]';

    private const PADRAO = '/\b(drop\s+table|union\s+select|delete\s+from|insert\s+into|truncate\s+table)\b/i';

    /** Há frase de ataque em algum texto? Perguntas assim não vão para o Analista (o servidor recusaria o pacote inteiro). */
    public static function contem(mixed $valor): bool
    {
        if (is_string($valor)) {
            return (bool) preg_match(self::PADRAO, $valor);
        }
        if (is_array($valor)) {
            foreach ($valor as $v) {
                if (self::contem($v)) {
                    return true;
                }
            }
        }

        return false;
    }

    public static function limpar(mixed $valor): mixed
    {
        if (is_string($valor)) {
            return preg_match(self::PADRAO, $valor) ? self::AVISO : $valor;
        }
        if (is_array($valor)) {
            return array_map(fn ($v) => self::limpar($v), $valor);
        }

        return $valor;
    }
}
