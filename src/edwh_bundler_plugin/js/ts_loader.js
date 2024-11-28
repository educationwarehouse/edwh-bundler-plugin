let __namespace__;


const System = {
    __dependencies__: {},

    register(namespace, lst, callback) {
        // lst is used to store dependencies/imports, result.setters should be used to include these externals
        let vars;

        if (namespace === '__main__') {
            vars = window
        } else {
            vars = this.__dependencies__[namespace] = {}
        }

        let exports = {}
        let result = callback((key, value) => {
            exports[key] = value
        })

        for (const [idx, name] of lst.entries()) {
            const dep = this.__dependencies__[name];
            result.setters[idx](dep);
        }

        result.execute(); // start any global code
        for (let [key, value] of Object.entries(exports)) {
            vars[key] = value
        }
    }
}
