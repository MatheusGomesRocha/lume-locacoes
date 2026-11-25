<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware) {
        // Limite de 60 requisições por minuto na API (o limitador "api" está no AppServiceProvider).
        $middleware->api(prepend: ['throttle:api']);
    })
    ->withExceptions(function (Exceptions $exceptions) {
        // RegraDeNegocioException já sabe se transformar em JSON (ver o próprio arquivo).
    })->create();
