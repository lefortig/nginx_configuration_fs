#!/usr/bin/env python
# -*- coding: utf8 -*-

import 	pprint

import 	colorama

import	re

import  regex

import  rfc3987

import	collections

import	json

import 	os

import	sys

import  twisted.scripts._twistd_unix

import  threading

from    plone.synchronize       import  synchronized

import 	fuse

########################
# Gestion de cache plone
########################

def cache_key( fun, instance, *args ):

#    print( 
#        colorama.Fore.RED + 		\
#	repr( fun ) +			\
#        colorama.Fore.RESET + 		\
#        colorama.Fore.YELLOW + 		\
#	repr( instance ) +		\
#        colorama.Fore.RESET + 		\
#        colorama.Fore.CYAN + 		\
#	repr( args ) +			\
#        colorama.Fore.RESET
#    )

    return (instance.__class__,) + args

cache_container_agnostic_configuration          = {}
cache_container_ssl_configuration          	= {}
cache_container_url2app_configuration          	= {}
cache_container_nginx_fs                        = {}



####################
# Traitement des URL
####################

URI_rfc3987                        =       rfc3987.get_compiled_pattern('^%(URI)s$')

def common_process_uri(
    le_root_configuration,
    d,
    current_line,
    current_server,
    current_port,
    current_mapping_type,
    l_bad_configurations,
    suffixwith
):
    key_uri, uri                    = [ ( k, v ) for k, v in d.items() if k.startswith( suffixwith ) and k.endswith( 'URI' ) ][ 0 ]

    d_rfc3987 = URI_rfc3987.match( uri ).groupdict()

    if not re.match(
        'http|https',
        d_rfc3987[ 'scheme' ]
    ):
        l_bad_configurations.append(
            (
                 'scheme %s invalid in %s from %s' % (
                     d_rfc3987[ 'scheme' ],
                     uri,
                     current_line
                 ),
                 le_root_configuration(),
                 current_server,
                 current_port,
                 current_mapping_type
            )
        )
        raise Exception

    if d_rfc3987[ 'port' ] is None:
        if d_rfc3987[ 'scheme' ]    == 'http':
            d_rfc3987.update( { 'port' : 80 } )
        elif d_rfc3987[ 'scheme' ] == 'https':
            d_rfc3987.update( { 'port' : 443 } )
        else:
            raise Exception


    uri = ''
    uri += d_rfc3987[ 'scheme' ] + ':'
    uri += '//'
    if  d_rfc3987.get( 'userinfo' ):
        uri += d_rfc3987[ 'userinfo' ] + '@'
    uri += d_rfc3987[ 'host' ]
    uri += ':%s' % ( d_rfc3987[ 'port' ] )
    uri += d_rfc3987[ 'path' ] or ''
    if  d_rfc3987.get( 'query' ):
        uri += '?' + d_rfc3987[ 'query' ]
    if  d_rfc3987.get( 'fragment' ):
        uri += '#' + d_rfc3987[ 'fragment' ]

    d[ key_uri ]                            = uri
    d[ '%sscheme' % ( suffixwith ) ]        = d_rfc3987[ 'scheme' ]
    d[ '%shost' % ( suffixwith ) ]          = d_rfc3987[ 'host' ]
    d[ '%sport' % ( suffixwith ) ]          = d_rfc3987[ 'port' ]
    d[ '%spath' % ( suffixwith ) ]          = d_rfc3987[ 'path' ]
    d[ '%squery' % ( suffixwith ) ]         = d_rfc3987.get( 'query' )
    d[ '%sfragment' % ( suffixwith ) ]      = d_rfc3987.get( 'fragment' )
    d[ '%suserinfo' % ( suffixwith ) ]      = d_rfc3987.get( 'userinfo' )

def listen_ssl_process_uri(
    le_root_configuration,
    le_ssl_configuration,
    d,
    current_line,
    current_server,
    current_port,
    current_mapping_type,
    l_bad_configurations,
    suffixwith
):
    """
       listen_ssl_process_uri must follow common_process_uri
    """
    key_scheme, scheme      = [ ( k, v ) for k, v in d.items() if k.startswith( suffixwith ) and k.endswith( 'scheme' ) ][ 0 ]

    key_uri, uri            = [ ( k, v ) for k, v in d.items() if k.startswith( suffixwith ) and k.endswith( 'URI' ) ][ 0 ]

    expected_scheme         = 'https' if le_ssl_configuration().have_ssl( current_server, current_port ) else 'http'

    if scheme <> expected_scheme:
        l_bad_configurations.append(
            (
                'scheme %s expected in %s from %s' % (
                     expected_scheme,
                     uri,
                     current_line
                ),
                le_root_configuration(),
                current_server,
                current_port,
                current_mapping_type
            )
        )
        raise Exception


########################################
# Gestion de la signature des structures
# Mise en place de la possibilite de
# masquer certaines informations
# lors du calcul de las signature
########################################

class DictWithMaskableKeys( collections.MutableMapping ):

    def __init__( self, data, l_masked_keys ):
        self._data             	= data
        self._l_masked_keys 	= l_masked_keys

    def __len__( self ):
        return len( self._data )

    def __iter__( self ):
        return iter( self._data )

    def __setitem__( self, k, v ):
        if k not in self._data:
            raise KeyError( k )

        self._data[k] = v

    def __delitem__( self, k ):
        if k not in self._data:
            raise KeyError( k )

        self._data.delitem__( k )

    def __getitem__( self, k ):
        return self._data[ k ]

    def __contains__( self, k ):
        return k in self._data

    def itervisibleitems( self ):

        return \
            dict(
               [
                  ( key, value )
                  for key, value in self._data.iteritems()
                  if key not in self._l_masked_keys
               ]
            )


class DictWithMaskableKeysEncoder( json.JSONEncoder ):

    def default( self, obj ):
        if isinstance( obj, DictWithMaskableKeys ):
          return obj.itervisibleitems()
        return json.JSONEncoder.default( self, obj )


######################################
# Gestion du detachement des processus
# avec twisted
# Mise en place du serveur telnet de
# supervision
#####################################

class DaemonRunner( twisted.scripts._twistd_unix.UnixApplicationRunner ):

    def __init__(
        self,
        le_preApplication,
        l_le_startApplication,
    ):

        class FakeConfig(dict):
            """Wrapper class to make a options object look like dictionary
            for twistd stuff
            """

            def __init__(self, options):

                self.options = options

            def __getitem__(self, key):

                return getattr(self.options, key)

        class Options:

            def get( self, key, default = None ):

                return getattr( self, key, default )

        options                         = Options()

        options.profile                 = ''
        options.chroot                  = None
        options.rundir                  = '.'
        options.umask                   = 022
        options.pidfile                 = None
        options.debug                   = False

        self.options                    = options

        twisted.scripts._twistd_unix.UnixApplicationRunner.__init__(
            self,
            self.options
        )

        self.config                     = FakeConfig( options )

        self.application                = None

        self._le_preApplication         = le_preApplication

        self._l_le_startApplication     =                       \
            l_le_startApplication


    def preApplication( self ):

        self._startApplicationParams    =                       \
            self._le_preApplication()

        self.options.nodaemon           =                       \
            self._startApplicationParams.get(                   \
                'nodaemon',
                False
            )

        twisted.scripts._twistd_unix.UnixApplicationRunner.preApplication(
            self
        )

    def run(self):

        self.preApplication()

        self.postApplication()

    def startApplication(self, application ):

        try:
            self.setupEnvironment(
                self.config[ 'chroot' ],
                self.config[ 'rundir' ],
                self.config[ 'nodaemon' ],
                self.config[ 'umask' ],
                self.config[ 'pidfile' ],
            )
        except Exception, e:
            # We may have already forked/daemonized at this point, so lets hope
            # that logging was setup properly otherwise, we may never know...
            print >>sys.stderr, "Error setting up environment: %r" % e
            sys.exit( -2 )

        l_process	= []

        map(
            lambda le: le( self._startApplicationParams, l_process ),
            self._l_le_startApplication,
        )

class TwistedDaemon( object ):

    _l_process_lock			= threading.RLock()
    _d_event_lock			= threading.RLock()
    _listen_lock			= threading.Lock()

    def __init__(
        self,
        bootstrap,
        l_process,
         **kwargs
    ):

        self._bootstrap                 = bootstrap
        self._l_process			= l_process
        self._kwargs                    = kwargs

    def __getattribute__( self, attr ):

        try:
            return                                      \
                object.__getattribute__(                \
                    self,                               \
                    '_kwargs'                           \
                )[ attr ]
        except:
            try:
                return object.__getattribute__(         \
                    self,                               \
                    attr                                \
                )
            except Exception, e:
                raise AttributeError( '%r' %e )

    def get_kwargs( self ):
        return self._kwargs
    kwargs                      = property( get_kwargs, None, None )

    def get_bootstrap( self ):
        return self._bootstrap
    bootstrap                   = property( get_bootstrap, None, None )

    def get_l_process( self ):
        return self._l_process
    l_process                   = property( get_l_process, None, None )

    def run(
        self
        ):

        from twisted.internet import protocol
        from twisted.internet import reactor

        class ProcessTwistedDaemonProtocol( protocol.ProcessProtocol ):

            def __init__( self, l_process ):

                with TwistedDaemon._l_process_lock:
                    self._l_process		= l_process

                with TwistedDaemon._d_event_lock:
                    self._d_events		= {}

            def get_d_events( self ):
                return self._d_events
            d_events 			= property( get_d_events, None, None )

            @synchronized( TwistedDaemon._d_event_lock )
            def add_outReceived( self, to, le ):
                self.d_events.setdefault( 'out', {} ).setdefault( to, le )

            @synchronized( TwistedDaemon._d_event_lock )
            def add_errReceived( self, to, le ):
                self.d_events.setdefault( 'err', {} ).setdefault( to, le )

            @synchronized( TwistedDaemon._d_event_lock )
            def del_outReceived( self, to ):
                del( self.d_events[ 'out' ][ to ] )

            @synchronized( TwistedDaemon._d_event_lock )
            def del_errReceived( self, to ):
                del( self.d_events[ 'err' ][ to ] )

            def connectionMade( self ):

                with TwistedDaemon._l_process_lock:
                    self._l_process.append( self )

                sys.stderr.write( "PP connectionMade!" + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )
                #self.transport.closeStdin() # tell them we're done

            def outReceived( self, data ):

                sys.stderr.write( 'PP out %s' % data + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )
                sys.stderr.write( "PP %r" % self.d_events )

                with TwistedDaemon._d_event_lock:
                     map(
                         lambda le: le( data ),
                         self.d_events.get( 'out', {} ).values()
                     )

            def errReceived( self, data ):

                sys.stderr.write( 'PP err %s' % data + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )
                sys.stderr.write( "PP %r" % self.d_events )

                with TwistedDaemon._d_event_lock:
                     map(
                         lambda le: le( data ),
                         self.d_events.get( 'err', {} ).values()
                     )

            def inConnectionLost( self ):
                sys.stderr.write( "PP inConnectionLost! stdin is closed! (we probably did it)" + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )

            def outConnectionLost( self ):
                sys.stderr.write( "PP outConnectionLost! The child closed their stdout!" + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )

            def errConnectionLost( self ):
                sys.stderr.write( "PP errConnectionLost! The child closed their stderr." + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )

            def processExited( self, reason ):
                sys.stderr.write( "PP processExited, status %d" % (reason.value.exitCode,) + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )

            def processEnded( self, reason ):

                with TwistedDaemon._l_process_lock:
                    self._l_process.remove( self )

                sys.stderr.write( "PP processEnded, status %d" % (reason.value.exitCode,) + os.linesep )
                sys.stderr.write( "PP quitting" + os.linesep )
                sys.stderr.write( "PP %r" % self._l_process + os.linesep )

                if not self._l_process:
                   reactor.stop()

        ptdp 	= ProcessTwistedDaemonProtocol( self.l_process )


        class Telnet( protocol.Protocol ):

            def connectionMade( self ):

                sys.stderr.write( 'TT connection made' + os.linesep )

                self.factory.ptdp.add_outReceived( self, lambda data: self.transport.write( data ) )
                self.factory.ptdp.add_errReceived( self, lambda data: self.transport.write( data ) )

            def dataReceived( self, data ):

                sys.stderr.write( 'TT data received' + os.linesep )
                self.factory.ptdp.transport.write( data )

            def connectionLost( self, reason ):

                sys.stderr.write( 'TT connection lost' + os.linesep )

                self.factory.ptdp.del_outReceived( self )
                self.factory.ptdp.del_errReceived( self )


        class TelnetFactory( protocol.Factory ):

            protocol		= Telnet

            def __init__( self, ptdp ):

                self._ptdp	= ptdp

            def get_ptdp( self ):

                return self._ptdp

            ptdp = property( get_ptdp, None, None )

        with TwistedDaemon._listen_lock:

            telnet_server 	= 		\
                reactor.listenTCP(
                    0,
                    TelnetFactory( ptdp )
                )

            # Alimentation de la variable permetatnt de construire
            # un fsnmae contextuel
            self.kwargs.update(
                {
                    'fsname':
                        '%i' % telnet_server._realPortNumber
                }
            )

        reactor.callWhenRunning(
            reactor.spawnProcess,
            ptdp,
            sys.executable,
            (
                sys.executable,
                '-c',
                self.bootstrap % ( self.kwargs ),
            ),
            usePTY              = 1,
        )


####################################
# Limitation de possibilites de Fuse
####################################

class ContextualizedFUSE( fuse.FUSE ):

    __L_FORBIDDEN_FUSE_OPTIONS__             	= 		\
        (
            'foreground',
            'sync',
            'async',
            'allow_other',
            'sync_read',
            'async_read',
            'encoding',
        )

    __D_DEFAULT_FUSE_OPTIONS__               		= 	\
        {
            'foreground': 	True,
            'allow_other': 	True,
            'sync_read': 	True,
            'sync': 		True,
            'encoding':		'utf-8',
        }


    __L_AUTHORIZED_SUPPLEMENTARIES_FUSE_OPTIONS__ 	= 	\
        (
            'fsname',
        )

    def __init__(
        self,
        operations,
        mountpoint,
        named_mount_options,
        **kwargs
    ):
        if kwargs.get( 'fsname' ):
            kwargs[ 'fsname' ] =                		\
               '%s_%s' % (
                   operations.__class__.__name__,
                   kwargs[ 'fsname' ]
            )

        fuse.FUSE.__init__(
            self,
            operations,
            mountpoint,
            **dict(
                [
                    ( k, v )
                    for k, v in
                    (
                        dict(
                            ( lambda param:
                                ( param.split( '=' )[ 0 ], param.split( '=' )[ 1 ] )
                                if len( param.split( '=' ) ) == 2
                                else ( param, True )
                            )( param )
                            for param in named_mount_options.split(',')
                        )
                        if named_mount_options <> ''
                        else {}
                    ).iteritems()
                    if k not in 							\
                        ContextualizedFUSE.__L_FORBIDDEN_FUSE_OPTIONS__ + 		\
                        operations.__L_FORBIDDEN_NAMED_MOUNT_OPTIONS__
                ] +
                [
                    ( k, v )
                    for k, v
                    in kwargs.iteritems()
                    if k in 									\
                        ContextualizedFUSE.__L_AUTHORIZED_SUPPLEMENTARIES_FUSE_OPTIONS__ +	\
                        operations.__L_AUTHORIZED_SUPPLEMENTARIES_FUSE_OPTIONS__
                ] +
                ContextualizedFUSE.__D_DEFAULT_FUSE_OPTIONS__.items() +
                operations.__D_DEFAULT_NAMED_MOUNT_OPTIONS__.items()
            )
        )
