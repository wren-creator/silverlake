**free
// REGRPT.RPGLE -- prints the payroll register, every employee and a
// total. Run by payroll staff, who may read PAYROLL themselves. The
// printer file sends it to QPRINT, which is where every report goes when
// nobody says otherwise, and QPRINT lets anyone read what is on it.

dcl-f payroll keyed;
dcl-f regrpt printer oflind(*inof);

dcl-s tot packed(9:0);

write heading;

setll *loval payroll;
read payroll;
dow not %eof(payroll);
  if *inof;
    write heading;
    *inof = *off;
  endif;
  tot += salary;
  write detail;
  read payroll;
enddo;

write total;
*inlr = *on;
return;
