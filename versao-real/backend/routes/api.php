<?php

use App\Http\Controllers\ChatController;
use App\Http\Controllers\ChatLogController;
use App\Http\Controllers\ClienteController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\OrcamentoController;
use App\Http\Controllers\PagamentoController;
use App\Http\Controllers\ProdutoController;
use Illuminate\Support\Facades\Route;

Route::get('health', fn () => ['status' => 'ok']);

Route::get('dashboard', DashboardController::class);

Route::apiResource('clientes', ClienteController::class);
Route::apiResource('produtos', ProdutoController::class);

Route::apiResource('orcamentos', OrcamentoController::class);
Route::post('orcamentos/{orcamento}/enviar', [OrcamentoController::class, 'enviar']);
Route::post('orcamentos/{orcamento}/aprovar', [OrcamentoController::class, 'aprovar']);
Route::post('orcamentos/{orcamento}/finalizar', [OrcamentoController::class, 'finalizar']);
Route::post('orcamentos/{orcamento}/cancelar', [OrcamentoController::class, 'cancelar']);

Route::get('pagamentos', [PagamentoController::class, 'index']);
Route::post('pagamentos/{pagamento}/baixar', [PagamentoController::class, 'baixar']);

Route::get('chat/sugestoes', [ChatController::class, 'sugestoes']);
Route::post('chat', [ChatController::class, 'perguntar']);

Route::get('chat-logs', [ChatLogController::class, 'index']);
Route::post('chat-logs', [ChatLogController::class, 'store']);
Route::patch('chat-logs/{chatLog}', [ChatLogController::class, 'update']);
Route::delete('chat-logs', [ChatLogController::class, 'destroy']);
