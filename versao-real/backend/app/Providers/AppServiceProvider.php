<?php

namespace App\Providers;

use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        //
    }

    public function boot(): void
    {
        // 10 tentativas de login por minuto por e-mail + IP: trava adivinhação de senha
        RateLimiter::for('login', fn (Request $request) => Limit::perMinute(10)->by(mb_strtolower((string) $request->input('email')).'|'.$request->ip()));
        RateLimiter::for('api', fn (Request $request) => Limit::perMinute(60)->by($request->user()?->id ?: $request->ip()));
    }
}
