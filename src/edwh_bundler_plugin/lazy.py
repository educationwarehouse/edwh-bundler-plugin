import importlib


class JIT:
    """
    This just in time class allows 'importing' packages that have not been installed yet.
    They will be installed by invoke's pre-tasks, but the import happens before that.
    This class catches these 'imports' and provides a pseudo package or module.
    Package:
        > sass = JIT('sass')
        > sass.compile(...)
        Uses __getattr__ to catch 'compile' and execute it on the actual sass package (
        imported by importlib and stored in self.package)
        > sass(...)
        uses __call__ to pass the args to the __call__ of the sass module.
    Method:
        > jsmin = JIT('rjsmin', 'jsmin')
        > jsmin(...)
        Uses __call__ to forward the arguments to the jsmin method (stored in self.method) of the rjsmin module (
        stored in self.package
        )
    """

    def __init__(self, package_name, method_name=None):
        self.package_name = package_name
        self.method_name = method_name
        self.package = None
        self.method = None

    def __call__(self, *args, **kwargs):
        if self.method_name:
            # JIT method (with method_name)
            if not self.method:
                self.__load_method()

            return self.method(*args, **kwargs)
        else:
            if not self.package:
                self.__load_package()
            self.package(*args, **kwargs)

    def __repr__(self):
        return f"<JustInTIme loaded {self.package}.{self.method}>"

    def __getattr__(self, item):
        # JIT package (without method_name)
        # works like a package: sass = JIT(...); sass.compile(...)
        if not self.package:
            self.__load_package()

        return getattr(self.package, item)

    def __load_method(self):
        if not self.package:
            self.__load_package()
        self.method = getattr(self.package, self.method_name)

    def __load_package(self):
        self.package = importlib.import_module(self.package_name)
