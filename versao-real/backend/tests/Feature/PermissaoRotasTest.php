<?php

namespace Tests\Feature;

use App\Models\ChatLog;
use App\Models\FaqItem;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\Concerns\CriaDados;
use Tests\TestCase;

/** Cada rota de dados só abre com uma das permissões abaixo (e fecha com 403 para quem não tem nenhuma). */
class PermissaoRotasTest extends TestCase
{
    use CriaDados;
    use RefreshDatabase;

    /** [método, uri com {chaves}, permissões que liberam] */
    public static function rotas(): array
    {
        $m = ['clientes.ver', 'orcamentos.criar', 'orcamentos.editar'];

        return [
            'painel' => ['getJson', '/api/dashboard', ['painel.ver']],
            'clientes listar' => ['getJson', '/api/clientes', $m],
            'clientes ver' => ['getJson', '/api/clientes/{cliente}', ['clientes.ver']],
            'clientes criar' => ['postJson', '/api/clientes', ['clientes.criar']],
            'clientes editar' => ['putJson', '/api/clientes/{cliente}', ['clientes.editar']],
            'clientes excluir' => ['deleteJson', '/api/clientes/{cliente}', ['clientes.excluir']],
            'produtos listar' => ['getJson', '/api/produtos', ['produtos.ver', 'orcamentos.criar', 'orcamentos.editar']],
            'produtos ver' => ['getJson', '/api/produtos/{produto}', ['produtos.ver']],
            'produtos criar' => ['postJson', '/api/produtos', ['produtos.criar']],
            'produtos editar' => ['putJson', '/api/produtos/{produto}', ['produtos.editar']],
            'produtos excluir' => ['deleteJson', '/api/produtos/{produto}', ['produtos.excluir']],
            'orcamentos listar' => ['getJson', '/api/orcamentos', ['orcamentos.ver', 'financeiro.ver']],
            'orcamentos ver' => ['getJson', '/api/orcamentos/{orcamento}', ['orcamentos.ver']],
            'orcamentos criar' => ['postJson', '/api/orcamentos', ['orcamentos.criar']],
            'orcamentos editar' => ['putJson', '/api/orcamentos/{orcamento}', ['orcamentos.editar']],
            'orcamentos excluir' => ['deleteJson', '/api/orcamentos/{orcamento}', ['orcamentos.excluir']],
            'orcamentos enviar' => ['postJson', '/api/orcamentos/{orcamento}/enviar', ['orcamentos.enviar']],
            'orcamentos aprovar' => ['postJson', '/api/orcamentos/{orcamento}/aprovar', ['orcamentos.aprovar']],
            'orcamentos finalizar' => ['postJson', '/api/orcamentos/{orcamento}/finalizar', ['orcamentos.finalizar']],
            'orcamentos cancelar' => ['postJson', '/api/orcamentos/{orcamento}/cancelar', ['orcamentos.cancelar']],
            'financeiro ver' => ['getJson', '/api/pagamentos', ['financeiro.ver']],
            'financeiro baixar' => ['postJson', '/api/pagamentos/{pagamento}/baixar', ['financeiro.baixar']],
            'chat sugestoes' => ['getJson', '/api/chat/sugestoes', ['assistente.usar']],
            'chat perguntar' => ['postJson', '/api/chat', ['assistente.usar']],
            'chat-logs registrar' => ['postJson', '/api/chat-logs', ['assistente.usar']],
            'chat-logs avaliar' => ['patchJson', '/api/chat-logs/{chatLog}', ['assistente.usar']],
            'chat-logs listar' => ['getJson', '/api/chat-logs', ['assistente.conversas']],
            'chat-logs apagar' => ['deleteJson', '/api/chat-logs', ['assistente.conversas']],
            // Só o master (nenhum grupo libera): ver FaqApiTest.
            'faq listar' => ['getJson', '/api/faq-itens', []],
            'faq criar' => ['postJson', '/api/faq-itens', []],
            'faq editar' => ['putJson', '/api/faq-itens/{faqItem}', []],
            'faq excluir' => ['deleteJson', '/api/faq-itens/{faqItem}', []],
            // Evolução assistida: o catálogo é de quem usa o chat; analisar e decidir, só o master (ver EvolucaoApiTest).
            'evolucao catalogo' => ['getJson', '/api/evolucao/catalogo', ['assistente.usar']],
            'evolucao listar' => ['getJson', '/api/evolucao', []],
            'evolucao analisar' => ['postJson', '/api/evolucao/analisar', []],
            'evolucao decidir' => ['postJson', '/api/evolucao/EV-0001/decidir', []],
            'evolucao desativar' => ['postJson', '/api/evolucao/EV-0001/desativar', []],
        ];
    }

    protected function setUp(): void
    {
        parent::setUp();
        Http::fake(['ia.test/*' => Http::response(['resposta' => 'ok'])]);
    }

    private function uri(string $modelo): string
    {
        $o = $this->orcamento();
        $trocas = [
            '{cliente}' => $this->cliente()->id,
            '{produto}' => $this->produto()->id,
            '{orcamento}' => $o->id,
            '{pagamento}' => $this->pagamento($o)->id,
            '{faqItem}' => FaqItem::create(['modulo' => 'Acesso', 'pergunta' => 'Pergunta de teste', 'resposta' => 'Resposta de teste', 'palavras_chave' => []])->id,
            '{chatLog}' => ChatLog::create(['pergunta' => 'p', 'resposta' => 'r', 'tipo' => 'ajuda'])->id,
        ];

        return strtr($modelo, $trocas);
    }

    #[DataProvider('rotas')]
    public function test_sem_nenhuma_permissao_a_rota_responde_403(string $metodo, string $modelo): void
    {
        $uri = $this->uri($modelo);
        $this->entrarComo($this->criarUsuario([]));

        $this->$metodo($uri, [])->assertForbidden();
    }

    #[DataProvider('rotas')]
    public function test_com_a_permissao_a_rota_deixa_passar(string $metodo, string $modelo, array $permissoes): void
    {
        $uri = $this->uri($modelo);

        foreach ($permissoes as $i => $permissao) {
            $this->entrarComo($this->criarUsuario([$permissao], 'usuario', "p{$i}@lume.test"));

            $status = $this->$metodo($uri, [])->status();

            $this->assertNotContains($status, [401, 403], "$permissao deveria liberar $metodo $modelo (veio $status)");
        }
    }
}
