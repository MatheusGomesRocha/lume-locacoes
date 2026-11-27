<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'mailgun' => [
        'domain' => env('MAILGUN_DOMAIN'),
        'secret' => env('MAILGUN_SECRET'),
        'endpoint' => env('MAILGUN_ENDPOINT', 'api.mailgun.net'),
        'scheme' => 'https',
    ],

    'postmark' => [
        'token' => env('POSTMARK_TOKEN'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    // API Python do assistente de ajuda (pasta ia-api)
    'ia' => [
        'url' => env('IA_API_URL', 'http://127.0.0.1:8001'),
        'token' => env('IA_API_TOKEN'),
    ],

    // Agent 4 (Aprovador) da evolução assistida. Modo: desligado | sombra (só registra, o master decide) | automatico (aprova sozinho).
    // O interruptor é EVOLUCAO_APROVADOR_MODO=desligado. Só passe para "automatico" depois de a taxa de acerto do modo sombra ser validada.
    'evolucao' => [
        'aprovador_modo' => env('EVOLUCAO_APROVADOR_MODO', 'sombra'),
        'aprovador_limite_dia' => (int) env('EVOLUCAO_APROVADOR_LIMITE_DIA', 10),     // aprovações automáticas por dia (UTC-3)
        'aprovador_por_execucao' => (int) env('EVOLUCAO_APROVADOR_POR_EXECUCAO', 3),  // propostas revisadas a cada execução (poupa a cota do modelo)
        'aprovador_amostra_a_cada' => (int) env('EVOLUCAO_APROVADOR_AMOSTRA_A_CADA', 5), // 1 em cada N aprovações automáticas vai para conferência
    ],

];
