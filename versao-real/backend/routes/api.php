<?php

use App\Http\Controllers\AuthController;
use App\Http\Controllers\ChatController;
use App\Http\Controllers\ChatLogController;
use App\Http\Controllers\ClienteController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\FaqController;
use App\Http\Controllers\GrupoController;
use App\Http\Controllers\OrcamentoController;
use App\Http\Controllers\PagamentoController;
use App\Http\Controllers\ProdutoController;
use App\Http\Controllers\UsuarioController;
use Illuminate\Support\Facades\Route;

// Públicas: só a verificação de saúde e o login.
Route::get('health', fn () => ['status' => 'ok']);
Route::post('login', [AuthController::class, 'login'])->middleware('throttle:login');

// Tudo o mais exige login e, em cada rota, a permissão do módulo (várias permissões = basta uma).
Route::middleware('autenticado')->group(function () {
    Route::post('logout', [AuthController::class, 'logout']);
    Route::get('eu', [AuthController::class, 'eu']);
    Route::put('eu', [AuthController::class, 'atualizarEu']);

    Route::get('dashboard', DashboardController::class)->middleware('pode:painel.ver');

    // Quem monta orçamentos precisa listar clientes e produtos para escolher.
    Route::get('clientes', [ClienteController::class, 'index'])->middleware('pode:clientes.ver,orcamentos.criar,orcamentos.editar');
    Route::get('clientes/{cliente}', [ClienteController::class, 'show'])->middleware('pode:clientes.ver');
    Route::post('clientes', [ClienteController::class, 'store'])->middleware('pode:clientes.criar');
    Route::put('clientes/{cliente}', [ClienteController::class, 'update'])->middleware('pode:clientes.editar');
    Route::delete('clientes/{cliente}', [ClienteController::class, 'destroy'])->middleware('pode:clientes.excluir');

    Route::get('produtos', [ProdutoController::class, 'index'])->middleware('pode:produtos.ver,orcamentos.criar,orcamentos.editar');
    Route::get('produtos/{produto}', [ProdutoController::class, 'show'])->middleware('pode:produtos.ver');
    Route::post('produtos', [ProdutoController::class, 'store'])->middleware('pode:produtos.criar');
    Route::put('produtos/{produto}', [ProdutoController::class, 'update'])->middleware('pode:produtos.editar');
    Route::delete('produtos/{produto}', [ProdutoController::class, 'destroy'])->middleware('pode:produtos.excluir');

    Route::get('orcamentos', [OrcamentoController::class, 'index'])->middleware('pode:orcamentos.ver,financeiro.ver');
    Route::get('orcamentos/{orcamento}', [OrcamentoController::class, 'show'])->middleware('pode:orcamentos.ver');
    Route::post('orcamentos', [OrcamentoController::class, 'store'])->middleware('pode:orcamentos.criar');
    Route::put('orcamentos/{orcamento}', [OrcamentoController::class, 'update'])->middleware('pode:orcamentos.editar');
    Route::delete('orcamentos/{orcamento}', [OrcamentoController::class, 'destroy'])->middleware('pode:orcamentos.excluir');
    Route::post('orcamentos/{orcamento}/enviar', [OrcamentoController::class, 'enviar'])->middleware('pode:orcamentos.enviar');
    Route::post('orcamentos/{orcamento}/aprovar', [OrcamentoController::class, 'aprovar'])->middleware('pode:orcamentos.aprovar');
    Route::post('orcamentos/{orcamento}/finalizar', [OrcamentoController::class, 'finalizar'])->middleware('pode:orcamentos.finalizar');
    Route::post('orcamentos/{orcamento}/cancelar', [OrcamentoController::class, 'cancelar'])->middleware('pode:orcamentos.cancelar');

    Route::get('pagamentos', [PagamentoController::class, 'index'])->middleware('pode:financeiro.ver');
    Route::post('pagamentos/{pagamento}/baixar', [PagamentoController::class, 'baixar'])->middleware('pode:financeiro.baixar');

    Route::get('chat/sugestoes', [ChatController::class, 'sugestoes'])->middleware('pode:assistente.usar');
    Route::post('chat', [ChatController::class, 'perguntar'])->middleware('pode:assistente.usar');

    Route::post('chat-logs', [ChatLogController::class, 'store'])->middleware('pode:assistente.usar');
    Route::patch('chat-logs/{chatLog}', [ChatLogController::class, 'update'])->middleware('pode:assistente.usar');
    Route::get('chat-logs', [ChatLogController::class, 'index'])->middleware('pode:assistente.conversas');
    Route::delete('chat-logs', [ChatLogController::class, 'destroy'])->middleware('pode:assistente.conversas');

    // Responder às perguntas sem resposta (base de ajuda): só o master, nunca por grupo.
    Route::middleware('master')->group(function () {
        Route::get('faq-itens', [FaqController::class, 'index']);
        Route::post('faq-itens', [FaqController::class, 'store']);
        Route::put('faq-itens/{faqItem}', [FaqController::class, 'update']);
        Route::delete('faq-itens/{faqItem}', [FaqController::class, 'destroy']);
    });

    // Usuários: só administradores e master, e ainda com a permissão do grupo.
    Route::middleware('admin')->group(function () {
        Route::get('usuarios', [UsuarioController::class, 'index'])->middleware('pode:usuarios.ver');
        Route::post('usuarios', [UsuarioController::class, 'store'])->middleware('pode:usuarios.criar');
        Route::put('usuarios/{usuario}', [UsuarioController::class, 'update'])->middleware('pode:usuarios.editar');
        Route::delete('usuarios/{usuario}', [UsuarioController::class, 'destroy'])->middleware('pode:usuarios.excluir');
        Route::get('grupos', [GrupoController::class, 'index']);
    });

    // Grupos: só o master.
    Route::middleware('master')->group(function () {
        Route::post('grupos', [GrupoController::class, 'store']);
        Route::put('grupos/{grupo}', [GrupoController::class, 'update']);
        Route::delete('grupos/{grupo}', [GrupoController::class, 'destroy']);
    });
});
