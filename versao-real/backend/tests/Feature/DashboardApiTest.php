<?php

namespace Tests\Feature;

use App\Services\DashboardService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

class DashboardApiTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    private function resumo(string $hoje = '2026-11-15'): array
    {
        return (new DashboardService())->resumo(Carbon::parse($hoje));
    }

    public function test_endpoint_devolve_a_estrutura_do_painel(): void
    {
        $this->getJson('/api/dashboard')->assertOk()->assertJsonStructure([
            'recebido_mes', 'a_receber', 'em_atraso', 'orcamentos_em_aberto',
            'recebido_por_mes', 'orcamentos_por_status', 'produtos_mais_alugados', 'proximos_eventos',
        ]);
    }

    public function test_sem_dados_tudo_zerado(): void
    {
        $r = $this->resumo();

        $this->assertSame(0.0, $r['recebido_mes']);
        $this->assertSame(0.0, $r['a_receber']);
        $this->assertSame(0.0, $r['em_atraso']);
        $this->assertCount(6, $r['recebido_por_mes']);
        $this->assertSame([], $r['proximos_eventos']);
    }

    public function test_totais_financeiros_separam_recebido_a_receber_e_atraso(): void
    {
        $o = $this->orcamento('aprovado');
        $this->pagamento($o, 'pago', '2026-11-01', '2026-11-03', 300);   // recebido no mês
        $this->pagamento($o, 'pago', '2026-10-01', '2026-10-20', 999);   // mês anterior: não conta
        $this->pagamento($o, 'pendente', '2026-11-15', null, 200);        // vence hoje: a receber
        $this->pagamento($o, 'pendente', '2026-12-01', null, 50);         // a receber
        $this->pagamento($o, 'pendente', '2026-11-14', null, 70);         // atrasado
        $this->pagamento($o, 'cancelado', '2026-11-01', null, 5000);      // ignorado

        $r = $this->resumo();

        $this->assertSame(300.0, $r['recebido_mes']);
        $this->assertSame(250.0, $r['a_receber']);
        $this->assertSame(70.0, $r['em_atraso']);
    }

    public function test_recebido_por_mes_cobre_seis_meses_em_ordem(): void
    {
        $o = $this->orcamento('aprovado');
        $this->pagamento($o, 'pago', '2026-06-01', '2026-06-10', 100);
        $this->pagamento($o, 'pago', '2026-05-01', '2026-05-10', 999); // fora da janela
        $this->pagamento($o, 'pago', '2026-11-01', '2026-11-10', 40);
        $this->pagamento($o, 'pago', '2026-11-02', '2026-11-12', 60);

        $meses = $this->resumo()['recebido_por_mes'];

        $this->assertSame(['2026-06', '2026-07', '2026-08', '2026-09', '2026-10', '2026-11'], array_column($meses, 'mes'));
        $this->assertSame([100.0, 0.0, 0.0, 0.0, 0.0, 100.0], array_column($meses, 'total'));
    }

    public function test_conta_orcamentos_em_aberto_e_por_status(): void
    {
        foreach (['rascunho', 'rascunho', 'enviado', 'aprovado', 'finalizado', 'cancelado'] as $s) {
            $this->orcamento($s);
        }

        $r = $this->resumo();

        $this->assertSame(3, $r['orcamentos_em_aberto']);
        $this->assertSame(
            ['rascunho' => 2, 'enviado' => 1, 'aprovado' => 1, 'finalizado' => 1, 'cancelado' => 1],
            array_column($r['orcamentos_por_status'], 'total', 'status')
        );
    }

    public function test_produtos_mais_alugados_conta_so_aprovados_e_finalizados_e_limita_a_cinco(): void
    {
        $produtos = [];
        for ($i = 1; $i <= 6; $i++) {
            $produtos[$i] = $this->produto(['nome' => "P$i"]);
            $this->orcamento('aprovado', itens: [[$produtos[$i], $i]]);
        }
        $this->orcamento('rascunho', itens: [[$produtos[1], 100]]); // não conta

        $lista = $this->resumo()['produtos_mais_alugados'];

        $this->assertCount(5, $lista);
        $this->assertSame('P6', $lista[0]['nome']);
        $this->assertSame(6, $lista[0]['quantidade']);
        $this->assertNotContains('P1', array_column($lista, 'nome'));
    }

    public function test_proximos_eventos_sao_aprovados_futuros_em_ordem_de_data(): void
    {
        $this->orcamento('aprovado', '2026-11-10', '2026-11-12', dados: ['evento' => 'Passado']);
        $this->orcamento('aprovado', '2026-12-20', '2026-12-21', dados: ['evento' => 'Depois']);
        $this->orcamento('aprovado', '2026-11-15', '2026-11-16', dados: ['evento' => 'Hoje']);
        $this->orcamento('enviado', '2026-11-18', '2026-11-19', dados: ['evento' => 'Não aprovado']);

        $eventos = $this->resumo()['proximos_eventos'];

        $this->assertSame(['Hoje', 'Depois'], array_column($eventos, 'evento'));
        $this->assertSame('Cliente Teste', $eventos[0]['cliente']);
    }
}
