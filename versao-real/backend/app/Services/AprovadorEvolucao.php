<?php

namespace App\Services;

use App\Models\EvolucaoProposta;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Agent 4 (Aprovador) da evolução assistida: revisa as propostas em aberto que ainda não têm parecer.
 *
 * Modos (config services.evolucao.aprovador_modo):
 *  - desligado: não faz nada (interruptor).
 *  - sombra:    chama a API, GUARDA o parecer e não decide nada. O master continua decidindo e a tela compara as duas decisões.
 *  - automatico: se o parecer for "aprovar", refaz as checagens fixas e ativa a consulta, até o limite diário; 1 em cada N vai para conferência.
 * Uma proposta nunca é revisada duas vezes (a coluna revisao fica preenchida): o job pode rodar de 5 em 5 minutos sem repetir gasto.
 */
class AprovadorEvolucao
{
    public const NOME = 'Agent de Aprovação';

    public function modo(): string
    {
        $m = (string) config('services.evolucao.aprovador_modo', 'sombra');

        return in_array($m, ['desligado', 'sombra', 'automatico'], true) ? $m : 'desligado'; // valor desconhecido = desligado (falha para o lado seguro)
    }

    private function api(int $segundos)
    {
        $http = Http::baseUrl(config('services.ia.url'))->timeout($segundos)->acceptJson();

        return config('services.ia.token') ? $http->withHeaders(['X-API-Token' => config('services.ia.token')]) : $http;
    }

    /** @return array{modo:string,revisadas:int,aprovadas_automaticamente:int,erros:int,pendentes_sem_parecer:int,mensagem:string} */
    public function executar(): array
    {
        $modo = $this->modo();
        $saida = ['modo' => $modo, 'revisadas' => 0, 'aprovadas_automaticamente' => 0, 'erros' => 0, 'pendentes_sem_parecer' => 0, 'mensagem' => ''];
        if ($modo === 'desligado') {
            $saida['mensagem'] = 'O Agent de Aprovação está desligado (EVOLUCAO_APROVADOR_MODO).';

            return $saida;
        }

        $abertas = EvolucaoProposta::query()->where('status', 'pendente')->whereNull('revisao')->orderBy('id');
        $saida['pendentes_sem_parecer'] = (clone $abertas)->count();
        foreach ($abertas->limit(max(1, (int) config('services.evolucao.aprovador_por_execucao', 3)))->get() as $p) {
            $parecer = $this->pedirParecer($p);
            if ($parecer === null) {
                $saida['erros']++;

                continue; // sem parecer ela continua em aberto e entra de novo na próxima execução
            }
            $p->update(['revisao' => $parecer + ['modo' => $modo], 'revisao_em' => now()]);
            $saida['revisadas']++;
            if ($modo === 'automatico' && ($parecer['decisao'] ?? null) === 'aprovar' && $this->aprovarSozinho($p->fresh())) {
                $saida['aprovadas_automaticamente']++;
            }
        }
        $saida['mensagem'] = $saida['revisadas'] ? "{$saida['revisadas']} proposta(s) revisada(s) no modo {$modo}." : ($saida['pendentes_sem_parecer'] ? 'Não consegui revisar agora; tento de novo na próxima execução.' : 'Nenhuma proposta em aberto para revisar.');

        return $saida;
    }

    private function pedirParecer(EvolucaoProposta $p): ?array
    {
        try {
            $r = $this->api(120)->post('/evolucao/revisar', ['relatorio' => $p->relatorio, 'catalogo' => EvolucaoProposta::specsAtivas()]);
        } catch (Throwable $e) {
            Log::error('Aprovador: falha ao chamar a API: ' . $e->getMessage());

            return null;
        }
        if (! $r->successful() || ! in_array($r->json('decisao'), ['aprovar', 'deixar_pendente', 'reprovar'], true)) {
            Log::error('Aprovador: a API respondeu ' . $r->status());

            return null;
        }

        return (array) $r->json();
    }

    /** Aprovações automáticas já feitas hoje (dia de Fortaleza). */
    public function aprovadasHoje(): int
    {
        $inicio = now('America/Fortaleza')->startOfDay()->utc();

        return EvolucaoProposta::query()->where('auto_aprovada', true)->where('decidida_em', '>=', $inicio)->count();
    }

    /** Ativa a consulta SÓ se o limite do dia permite e as checagens fixas, refeitas agora, não têm bloqueio (a mesma regra da aprovação do master). */
    private function aprovarSozinho(EvolucaoProposta $p): bool
    {
        if ($this->aprovadasHoje() >= (int) config('services.evolucao.aprovador_limite_dia', 10)) {
            return false; // passou do limite: fica pendente para o master
        }
        $spec = $p->relatorio['pacote']['spec'] ?? null;
        if (! $spec || $p->veredito !== 'aprovar_recomendado') {
            return false;
        }
        try {
            $c = $this->api(25)->post('/evolucao/checar', ['spec' => $spec, 'proposta' => ($p->relatorio['proposta'] ?? null) ?: new \stdClass(), 'catalogo' => EvolucaoProposta::specsAtivas()]);
        } catch (Throwable $e) {
            Log::error('Aprovador: falha ao refazer as checagens: ' . $e->getMessage());

            return false;
        }
        if (! $c->successful() || $c->json('bloqueio') !== false) {
            return false;
        }
        $cada = max(1, (int) config('services.evolucao.aprovador_amostra_a_cada', 5));
        $p->update([
            'status' => 'aprovada', 'ativa' => true, 'auto_aprovada' => true, 'decidida_por' => self::NOME, 'decidida_em' => now(),
            'amostra' => (EvolucaoProposta::where('auto_aprovada', true)->count() + 1) % $cada === 0,
        ]);

        return true;
    }
}
