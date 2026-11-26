<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        // Respostas que o master escreve a partir das perguntas sem resposta. A ia-api não guarda nada:
        // o ChatController manda estes itens junto de cada pergunta.
        Schema::create('faq_itens', function (Blueprint $t) {
            $t->id();
            $t->string('modulo', 40);
            $t->string('pergunta', 200);
            $t->text('resposta');
            $t->json('palavras_chave');
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('faq_itens');
    }
};
