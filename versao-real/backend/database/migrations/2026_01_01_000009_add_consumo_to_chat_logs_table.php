<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        // Quanto cada pergunta gastou do modelo e qual versão do assistente respondeu (base das métricas de custo e qualidade).
        Schema::table('chat_logs', function (Blueprint $t) {
            $t->unsignedInteger('tokens_entrada')->default(0);
            $t->unsignedInteger('tokens_saida')->default(0);
            $t->decimal('custo_usd', 10, 6)->default(0);
            $t->string('versao', 20)->nullable()->index();
        });
    }

    public function down(): void
    {
        Schema::table('chat_logs', function (Blueprint $t) {
            $t->dropColumn(['tokens_entrada', 'tokens_saida', 'custo_usd', 'versao']);
        });
    }
};
