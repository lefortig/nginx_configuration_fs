#!/usr/bin/env python
# -*- coding: utf8 -*-
import	os

import 	re

import  regex

import  rfc3987

import  threading

from    plone.synchronize       import  synchronized

from    plone.memoize       	import  volatile

import 	pprint

import 	dns.resolver

from 	contextlib   		import closing

import	colorama

import 	pyinotify

import  subprocess

import  hashlib

import	shared_infrastructure

import	extra_from_distrib

class URL2EntityConfiguration(
    shared_infrastructure.IAddToConfigurationWithMappingType
    ):

    _configurations_lock           	=       threading.RLock()

    _comment_pattern			= 	'''^\s*(?P<comment>#+)'''

    _url2entity_pattern			= 	\
        '''^\s*%s\s+(?:\/\*(?P<listening_uri_extra>[^\*]*)\*\/\s+){0,1}(?P<appcode>[A-Z][0-9]{2})\s+(?:/\*(?P<appcode_extra>[^\*]*)\*\/\s+){0,1}(?P<env>[0-9A-Z]{2})\s+(?:\/\*(?P<env_extra>[^\*]*)\*\/\s+){0,1}(?P<aera>[DV][0-9A-F])\s+(?:\/\*(?P<aera_extra>[^\*]*)\*\/\s+){0,1}(?P<virtual_ngv_num>[0-9]{2})(?:\s+\/\*(?P<virtual_ngv_num_extra>[^\*]*)\*\/){0,1}''' % (
            rfc3987.format_patterns(
                URI		= 'URI', 
            )['URI'],
    )

    @staticmethod
    def process_uri_for_url2entity(
        self,
        d,
        filepath,
        line,
        server,
        port,
        mapping_type,
        d_configurations,
        l_bad_configurations,
    ):
        shared_infrastructure.common_process_uri( 
            lambda: self._root_configuration,
            d, 
            line, 
            server, 
            port,
            mapping_type, 
            l_bad_configurations, 
            '',
        )

        shared_infrastructure.common_process_extra(
            lambda: self._root_configuration,
            d,
            line,
            server,
            port,
            mapping_type,
            l_bad_configurations,
            lambda: self._extra_from_distrib,
            'listening_uri_',
        )

        shared_infrastructure.listen_ssl_process_uri( 
            lambda: self._root_configuration,
            lambda: self._ssl_configuration,
            d, 
            line, 
            server, 
            port, 
            mapping_type,
            l_bad_configurations, 
            '',
        )

        shared_infrastructure.common_process_extra(
            lambda: self._root_configuration,
            d,
            line,
            server,
            port,
            mapping_type,
            l_bad_configurations,
            lambda: self._extra_from_distrib,
            'appcode_',
        )

        shared_infrastructure.common_process_extra(
            lambda: self._root_configuration,
            d,
            line,
            server,
            port,
            mapping_type,
            l_bad_configurations,
            lambda: self._extra_from_distrib,
            'env_',
        )

        shared_infrastructure.common_process_extra(
            lambda: self._root_configuration,
            d,
            line,
            server,
            port,
            mapping_type,
            l_bad_configurations,
            lambda: self._extra_from_distrib,
            'aera_',
        )

        shared_infrastructure.common_process_extra(
            lambda: self._root_configuration,
            d,
            line,
            server,
            port,
            mapping_type,
            l_bad_configurations,
            lambda: self._extra_from_distrib,
            'virtual_ngv_num_',
        )


        URL2EntityConfiguration.add_to_configuration( 
            d, 
            lambda d: {
                        'uri'			:
                            shared_infrastructure.str_with_extra(
                                d[ 'URI' ],
                                d[ 'listening_uri_extra' ],
                            ),
                        'appcode'		:
                            shared_infrastructure.str_with_extra(
                                d[ 'appcode' ],
                                d[ 'appcode_extra' ],
                            ),
                        'env'			:
                            shared_infrastructure.str_with_extra(
                                d[ 'env' ],
                                d[ 'env_extra' ],
                            ),
                        'aera'			:
                            shared_infrastructure.str_with_extra(
                                d[ 'aera' ],
                                d[ 'aera_extra' ],
                            ),
                        'virtual_ngv_num'	:
                            shared_infrastructure.str_with_extra(
                                d[ 'virtual_ngv_num' ],
                                d[ 'virtual_ngv_num_extra' ],
                            ),
                    }, 
            d_configurations,
            filepath,
            server, 
            port, 
            mapping_type,
            le_sort     = lambda x: ( x[ 'uri' ] )
        )


    def __init__(
        self, 
        root_configuration,
        resolver_conf,
        url2entity_filename,
        restart_nginx,
        ssl_configuration
    ):

        self._root_configuration	= root_configuration

        self._resolver_conf			= resolver_conf

        self._url2entity_filename			= url2entity_filename

        self._d_l_process_uri			= 				\
            {
                self._url2entity_filename		: URL2EntityConfiguration.process_uri_for_url2entity,
            }

        self._restart_nginx			= restart_nginx

        self._resolver				= None

        self._ssl_configuration			= ssl_configuration

        self._extra_from_distrib                =                               \
            extra_from_distrib.ExtraFromDistrib(
                self._restart_nginx
            )

        self._extra_from_distrib.register_cache_to_clear(
            shared_infrastructure.cache_container_agnostic_configuration
        )

        self._extra_from_distrib.register_configuration_to_reload(
            lambda: self.load_configurations( reload_without_version_control = False )
        )

        # Gestion de iNotify	
        wm 					= pyinotify.WatchManager() 
	mask 					= 				\
            pyinotify.IN_MODIFY 	| 					\
            pyinotify.IN_CREATE 	| 					\
            pyinotify.IN_DELETE 	| 					\
            pyinotify.IN_ATTRIB 	| 					\
            pyinotify.IN_MOVED_TO	|					\
            pyinotify.IN_MOVED_FROM


        class EventHandler( pyinotify.ProcessEvent ):


             def process_evt( o, event ):

                 def restart_nginx():

                      try:
    
                          subprocess.call( self._restart_nginx, shell = True )
    
                      except: 
    
                          self._l_bad_configurations.append( ( '%s error' % ( self._restart_nginx ), ) )
    
                          shared_infrastructure.cache_container_url2entity_configuration.clear()
                          shared_infrastructure.cache_container_nginx_fs.clear()

                 path_elements = \
                     filter( 
                         None, 
                         event.pathname[  
                             len( self._root_configuration.rstrip( os.sep ) + os.sep ):
                         ].split( os.sep )
                     )

                 if len( path_elements ) == 0 and event.mask & pyinotify.IN_ATTRIB:

                     self.load_configurations( reload_without_version_control = True )

                     return restart_nginx()

                 if 								\
                     event.dir						and	\
                     ( 
                         len( path_elements	) == 1			or	\
                         len( path_elements	) == 2
                     ):

                     if self.load_configurations( reload_without_version_control = False ):

                         return restart_nginx()


                 if len( path_elements ) != 3:
		     return None

                 if re.match( 
                     self._url2entity_filename, 
                     path_elements[ 2 ]
                 ): 

                     if self.load_configurations( reload_without_version_control = False ):

                         return restart_nginx()

                        
             process_IN_MODIFY 		= process_evt

             process_IN_CREATE		= process_evt

             process_IN_DELETE		= process_evt

             process_IN_ATTRIB		= process_evt

             process_IN_MOVED_TO	= process_evt

             process_IN_MOVED_FROM	= process_evt


        self._notifier 				= pyinotify.ThreadedNotifier( wm, EventHandler() )

        self._extra_from_distrib.register_notifier(
            self._notifier
        )

        self._notifier.coalesce_events()

        wm.add_watch( 
            self._root_configuration,
            mask, 
            rec=True,
            auto_add=True
        )
             
        self._d_configurations 			= {}

        self._l_bad_configurations 		= []

        self.load_configurations()


    def get_notifier( self ):
        return self._notifier
    notifier 			= property( get_notifier, None, None )


    @synchronized( _configurations_lock )
    def get_d_configurations( self ):
        return self._d_configurations
    d_configurations 		= property( get_d_configurations, None, None )


    @synchronized( _configurations_lock )
    def get_l_bad_configurations( self ):
        return self._l_bad_configurations
    l_bad_configurations 	= property( get_l_bad_configurations, None, None )


    @synchronized( _configurations_lock )
    def load_configurations( self, reload_without_version_control = False ):

        d_configurations 	= {}

        l_bad_configurations	= []

        # Obtention d'un resolveur base sur le resolv_conf fouri
        self._resolver		= dns.resolver.Resolver( self._resolver_conf )
        self._resolver.query    = shared_infrastructure.catch_NoNamesservers( self._resolver.query )

        # Recherche des serveurs
        for server in [ 
                       s 
                       for s 
                       in os.listdir( self._root_configuration )
                       if os.path.isdir( self._root_configuration.rstrip( os.sep ) + os.sep + s )
                      ]:

            # Si le nom ne correspond pas a un nom resolvable
            # la configuration n'est pas prise en compte
            if not self._resolver.query( server, 'A' ) and not self._resolver.query( server, 'AAAA' ):
                l_bad_configurations.append( ( '%s not resolvable' % ( server ), self._root_configuration, server, ) )
                continue


            try:
                # Si le repertoire ne contient pas de configuration
                # de port, la configuration n'est pas prise en compte
                if not os.listdir( self._root_configuration.rstrip( os.sep ) + os.sep + server ):
                    l_bad_configurations.append( ( '%s no port definition' % ( server ), self._root_configuration, server, ) )
                    continue
            except:
                # En cas de suppression de la racine
                # entre le listdir dans la boucle
                # et l'usage du server dans la cronstrcuion
                # de chemin, le repertoire server
                # peut avoir disparu.
                continue


            # Recherche des ports
            for port in os.listdir( self._root_configuration.rstrip( os.sep ) + os.sep + server ):

                # Si le repertoire ne correspond pas au format d'un nom de port
                # la configuration n'est pas prise en compte
                try:
                    if not( re.match( '\d{1,5}', port ) and int( port ) <= 65535 ):
                        raise Exception()
                except:
                        l_bad_configurations.append( ( '%s unvalid port format' % ( port ), self._root_configuration, server, port ) )
                        continue

                # Si aucun fichier de mapping
                # n'est present, la configuration n'est
                # pas prise en compte

                url2entity_filepath 		= 					\
                    self._root_configuration.rstrip( os.sep ) + os.sep + 		\
                    server + os.sep + 							\
                    port + os.sep + 							\
                    self._url2entity_filename


                def add_to_configuration(
                    mapping_type,
                    filepath,
                    pattern,
                    ):
                    try:
                        with closing( 
                            open( filepath )
                        ) as f:
        
                            for line in [ l.rstrip() for l in f.readlines() ]:
                                if re.match( URL2EntityConfiguration._comment_pattern, line ):
                                    continue
        
                                m = re.match( pattern, line )
                                if not m:
                                    l_bad_configurations.append( 
                                        ( 
                                            'invalid format %s' % ( line ), 
                                            self._root_configuration,
                                            server, 
                                            port, 
                                            mapping_type 
                                        ) 
                                    )
                                    continue
                               
                                try:
                                    self._d_l_process_uri[ mapping_type ]( 
                                        self,
                                        m.groupdict(),
                                        filepath,
                                        line,
                                        server,
                                        port, 
                                        mapping_type,
                                        d_configurations, 
                                        l_bad_configurations, 
                                    )
                                except:
                                    import traceback
                                    traceback.print_exc()
                                    continue

                                
                    except:
                        pass

                add_to_configuration( 
                    self._url2entity_filename, 	
                    url2entity_filepath, 	
                    URL2EntityConfiguration._url2entity_pattern, 		
                )


        if len( d_configurations ) == 0:
            l_bad_configurations.append( ( 'no configuration available', self._root_configuration, ) )

        if  													\
                 reload_without_version_control 								\
             or													\
                 self.get_version_configurations( d_configurations ) <> self.current_version_configurations	\
             or													\
                 hashlib.sha1( repr( l_bad_configurations ) ).hexdigest() <> hashlib.sha1( repr( self._l_bad_configurations ) ).hexdigest():

            self._d_configurations         =       d_configurations
            self._l_bad_configurations     =       l_bad_configurations
            shared_infrastructure.cache_container_url2entity_configuration.clear()
            shared_infrastructure.cache_container_nginx_fs.clear()

            return True

        return False


    get_id_configurations	=				\
        synchronized(
            _configurations_lock
        )(
            volatile.cache(
                shared_infrastructure.cache_key,
                lambda *args: 					\
                    shared_infrastructure.cache_container_url2entity_configuration
            )(
                shared_infrastructure.get_id_configurations
            )
        )
    id_configurations 	= property( get_id_configurations, None, None )


    filter_id_configurations	=				\
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args: 					\
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.filter_id_configurations
        )

    
    get_list_configurations_filenames   =                                       \
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args:                                                       \
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.get_list_configurations_filenames
        )


    get_last_time       =                                                       \
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args:                                                       \
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.get_last_time
        )


    get_last_atime      =                                                       \
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args:                                                       \
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.get_last_atime
        )


    get_last_ctime      =                                                       \
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args:                                                       \
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.get_last_ctime
        )


    get_last_mtime      =                                                       \
        volatile.cache(
            shared_infrastructure.cache_key,
            lambda *args:                                                       \
                shared_infrastructure.cache_container_url2entity_configuration
        )(
            shared_infrastructure.get_last_mtime
        )
    

    _get_version_configurations = 					\
        synchronized(
            _configurations_lock
        )(
            shared_infrastructure._get_version_configurations
    )
    get_version_configurations	= _get_version_configurations


    get_current_version_configurations = 				\
        synchronized(
            _configurations_lock
        )(
            shared_infrastructure.get_current_version_configurations
    )
    current_version_configurations	=				\
        property(
            get_current_version_configurations,
            None,
            None
        )
