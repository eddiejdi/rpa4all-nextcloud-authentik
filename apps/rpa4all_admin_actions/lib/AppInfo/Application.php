<?php

declare(strict_types=1);

namespace OCA\RPA4AllAdminActions\AppInfo;

use OCA\RPA4AllAdminActions\Listener\LoadAdminScriptsListener;
use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\AppFramework\Http\Events\BeforeTemplateRenderedEvent;

class Application extends App implements IBootstrap {
    public const APP_ID = 'rpa4all_admin_actions';

    public function __construct() {
        parent::__construct(self::APP_ID);
    }

    public function register(IRegistrationContext $context): void {
        $context->registerEventListener(
            BeforeTemplateRenderedEvent::class,
            LoadAdminScriptsListener::class,
        );
    }

    public function boot(IBootContext $context): void {
    }
}
