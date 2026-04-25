<?php

declare(strict_types=1);

return [
    'routes' => [
        [
            'name' => 'admin#relogin',
            'url'  => '/api/users/{userId}/relogin',
            'verb' => 'POST',
        ],
        [
            'name' => 'admin#scan',
            'url'  => '/api/users/{userId}/scan',
            'verb' => 'POST',
        ],
    ],
];
