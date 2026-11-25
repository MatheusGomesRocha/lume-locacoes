<?php

use Illuminate\Support\Facades\Route;

Route::get('/', fn () => response()->json(['servico' => 'Lume Locações - API', 'saude' => url('/api/health')]));
