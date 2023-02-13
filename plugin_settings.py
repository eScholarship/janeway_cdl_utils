from utils import models

PLUGIN_NAME = 'Janeway CDL Utils'
DISPLAY_NAME = 'janeway_cdl_utils'
DESCRIPTION = 'A janeway plugin that contains management commands used by CDL staff'
AUTHOR = 'California Digital Library'
VERSION = 0.1
SHORT_NAME = 'cdl_utils'
MANAGER_URL = 'cdl_utils_manager'

def install():
    ''' install this plugin '''
    plugin, created = models.Plugin.objects.get_or_create(
        name=SHORT_NAME,
        defaults={
            "enabled": True,
            "version": VERSION,
            "display_name": DISPLAY_NAME,
        }
    )

    if created:
        print('Plugin {0} installed.'.format(PLUGIN_NAME))
    elif plugin.version != VERSION:
        print('Plugin updated: {0} -> {1}'.format(VERSION, plugin.version))
        plugin.version = VERSION
        plugin.display_name = DISPLAY_NAME
        plugin.save()
    else:
        print('Plugin {0} is already installed.'.format(PLUGIN_NAME))

def register_for_events():
    '''register for events '''
    pass

def hook_registry():
    pass