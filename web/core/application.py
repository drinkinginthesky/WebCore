# encoding: utf-8

"""
"""

import                                          sys, os
from webob                                      import Request, Response


__all__ = ['Application']
log = __import__('logging').getLogger(__name__)



class Application(object):
    """A WSGI-compliant application base.
    
    This implements the basics nessicary to function as a WSGI application.
    
    Additionally, if you need more than a simple WSGI application (which can
    be used with other WSGI components) and would like a full-stack
    environment, you can use the factory method to create a complete
    environment.
    """
    
    def __init__(self, root, **kw):
        self.root = root
        self.config = kw
    
    @classmethod
    def factory(cls, gconfig=dict(), root=None, **config):
        """Build a full-stack framework around this WSGI application."""
        
        from paste.deploy.converters import asbool, asint
        from web.utils.object import get_dotted_object
        
        # Find, build, and configure our basic Application instance.
        if isinstance(root, basestring):
            root = get_dotted_object(root)
        app = cls(root(), **config)
        
        # Automatically use Buffet templating engines unless explicitly forbidden.
        if asbool(config.get('buffet', True)):
            from web.core.middleware import TemplatingMiddleware
            app = TemplatingMiddleware(app, config)
        
        # Automatically use ToscaWidgets unless explicitly forbidden (or simply not found).
        if asbool(config.get('widgets', True)):
            try:
                from tw.api import make_middleware as ToscaWidgetsMiddleware
                
                app = ToscaWidgetsMiddleware(app, config)
            
            except ImportError:
                log.warn("ToscaWidgets not installed, widget framework disabled.  You can remove this warning by specifying widgets=False in your config.")
        
        from paste.config import ConfigMiddleware
        app = ConfigMiddleware(app, config)
        
        # Automatically use beaker-supplied services unless explicitly forbidden (or simply not found).
        if asbool(config.get('beaker', True)):
            try:
                from beaker.middleware import SessionMiddleware, CacheMiddleware
                
                beakerconfig = dict([(i[7:], j) for i, j in config.iteritems() if i.startswith('beaker.')])
                
                app = SessionMiddleware(app, beakerconfig)
                app = CacheMiddleware(app, beakerconfig)
                
                del beakerconfig
            
            except ImportError:
                log.warn("Beaker not installed, sessions and caching disabled.  You can remove this warning by specifying beaker=False in your config.")
        
        try:
            if asbool(config.get('debug', False)):
                from weberror.evalexception import EvalException
                app = EvalException(app, gconfig)
            
            else:
                from weberror.errormiddleware import ErrorMiddleware
                app = ErrorMiddleware(app, gconfig)
        
        except ImportError:
            log.warn("WebError not installed, pretty error messages disabled.")
        
        
        from paste.registry import RegistryManager
        app = RegistryManager(app)
        
        
        if asbool(config.get('profile', False)):
            from paste.debug.profile import ProfileMiddleware
            app = ProfileMiddleware(app, log_filename=config.get('profile.file', 'profile.log.tmp'), limit=asint(config.get('profile.limit', 40)))
        
        # Enabled explicitly or while debugging so you can use Paste's HTTP server.
        if asbool(config.get('static', False)) or asbool(config.get('debug', False)):
            from paste.cascade import Cascade
            from paste.fileapp import DirectoryApp
            
            path = config.get('static.path', None)
            
            if path is None:
                # Attempt to discover the path automatically.
                path = __import__(root.__module__).__file__
                path = os.path.abspath(path)
                path = os.path.dirname(path)
                path = os.path.join(path, 'public')
            
            if not os.path.isdir(path):
                log.warn("Unable to find folder to serve static content from.  Please specify static.path in your config.")
            
            app = Cascade([DirectoryApp(path), app], catch=[401, 403, 404])
        
        # Enable compression if requested.
        if asbool(config.get('compress', False)):
            from paste.gzipper import middleware as GzipMiddleware
            app = GzipMiddleware(app, compress_level=asint(config.get('compress.level', 6)))
        
        return app
    
    def prepare(self, environment):
        import web.core
        
        if environment.has_key('paste.registry'):
            environment['paste.registry'].register(web.core.request, Request(environment))
            environment['paste.registry'].register(web.core.response, Response())
            
            if environment.has_key('beaker.cache'):
                environment['paste.registry'].register(web.core.cache, environment['beaker.cache'])
            
            if environment.has_key('beaker.session'):
                environment['paste.registry'].register(web.core.session, environment['beaker.session'])
    
    def __call__(self, environment, start_response):
        import web.core, web.utils
        
        try:
            self.prepare(environment)
            
            content = web.core.dispatch(self.root, web.core.request.path_info)
        
        except web.core.http.HTTPException, e:
            return e(environment, start_response)
        
        else:
            # TODO: Deal with unicode responses, file-like objects, and iterators.
            if not isinstance(content, basestring):
                return content
            
            web.core.response.body = content
        
        return web.core.response(environment, start_response)
