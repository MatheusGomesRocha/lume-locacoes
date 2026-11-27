<?php

namespace App\Console\Commands;

use App\Services\AprovadorEvolucao;
use Illuminate\Console\Command;

/** Agent 4: revisa as propostas em aberto. Agendado de 5 em 5 minutos (routes/console.php). */
class EvolucaoAprovar extends Command
{
    protected $signature = 'evolucao:aprovar';

    protected $description = 'Agent de Aprovação: revisa as propostas de evolução em aberto (modo sombra ou automático, ver EVOLUCAO_APROVADOR_MODO)';

    public function handle(AprovadorEvolucao $agent): int
    {
        $r = $agent->executar();
        $this->info($r['mensagem']);

        return self::SUCCESS;
    }
}
