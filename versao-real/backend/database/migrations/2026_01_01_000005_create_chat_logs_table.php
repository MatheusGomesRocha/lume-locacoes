<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('chat_logs', function (Blueprint $t) {
            $t->id();
            $t->string('pergunta', 500);
            $t->text('resposta');
            $t->string('tipo', 20)->index();
            $t->string('fonte_id', 100)->nullable();
            $t->string('ferramenta', 60)->nullable();
            $t->boolean('gerada_por_llm')->default(false);
            $t->boolean('em_cache')->default(false);
            $t->boolean('usou_contexto')->default(false);
            $t->unsignedInteger('latencia_ms')->default(0);
            $t->unsignedTinyInteger('voltas')->default(1);
            $t->string('feedback', 10)->nullable()->index();
            $t->string('desfecho', 12)->nullable();
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('chat_logs');
    }
};
