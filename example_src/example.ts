import {shared} from "./shared";

function echo<T>(a: T): T {
    console.log(a)
    return a
}

function add(a: number, b: number): number {
    return a + b
}

export function main() {
    // echo(add(echo(1), echo(2)))
    // echo(echo("Hi") + echo("Bye"))
    //
    // echo(add(echo("a"), echo("b")))

    shared()
}


console.log('--- ts file 1 ---')
main();
