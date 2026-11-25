<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('clientes', function (Blueprint $t) {
            $t->id();
            $t->string('nome');
            $t->string('tipo', 2)->default('PF'); // PF ou PJ
            $t->string('documento')->nullable();
            $t->string('email')->nullable();
            $t->string('telefone')->nullable();
            $t->string('cidade')->nullable();
            $t->text('observacoes')->nullable();
            $t->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('clientes');
    }
};
