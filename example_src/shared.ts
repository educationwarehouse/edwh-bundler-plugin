import {shared2} from "./shared2";

export function shared() {
    console.log('--- shared ---')
    shared2()
}

console.log('shared top-level')
