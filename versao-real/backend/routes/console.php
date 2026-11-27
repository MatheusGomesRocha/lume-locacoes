<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

/*
|--------------------------------------------------------------------------
| Console Routes
|--------------------------------------------------------------------------
|
| This file is where you may define all of your Closure based console
| commands. Each Closure is bound to a command instance allowing a
| simple approach to interacting with each command's IO methods.
|
*/

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

// Agent de Aprovação (evolução assistida): de 5 em 5 minutos revisa as propostas em aberto. O servidor precisa do cron do Laravel:
//   * * * * * cd /caminho/do/backend && php artisan schedule:run >> /dev/null 2>&1
// withoutOverlapping: uma execução lenta (a API de IA pode demorar) não se sobrepõe à próxima.
Schedule::command('evolucao:aprovar')->everyFiveMinutes()->withoutOverlapping(10)->runInBackground();
