let __namespace__;

const __dependencies__ = {}

const System = {
    register(lst, callback) {
        // lst is used to store dependencies/imports, result.setters should be used to include these externals
        let vars;

        if (__namespace__ === '__main__') {
            vars = window
        } else {
            vars = __dependencies__[__namespace__] = {}
        }

        let exports = {}
        let result = callback((key, value) => {
            exports[key] = value
        })

        for (const [idx, name] of lst.entries()) {
            const dep = __dependencies__[name];
            result.setters[idx](dep);
        }

        result.execute(); // start any global code
        for (let [key, value] of Object.entries(exports)) {
            vars[key] = value
        }
    }
}
